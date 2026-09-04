"""What a strategy package NEEDS, derived from its imports rather than from its name.

**Why this file exists.** `algos/tools/promote.py` freezes a bot's code into a snapshot, and it
copied one strategy directory. A strategy package borrows from its siblings by bare name, so a
snapshot for any bot that borrows could not import at all — found on 2026-09-04 by running the
extreme leg's promote for the first time, after which the resolver under test became the single
answer to *which files does this bot need*, shared by the copier and by the version count.

⚠ **A FAIL-WATCH AGAINST HEAD IS VACUOUS — the module did not exist** — so non-vacuity is by
MUTATION. ⚠ **THE MAP WAS RUN, NOT REASONED, and the first entry was written from inspection as
"4 red" and is actually 6** — the cycle and dotted-import cases each assert a BORROWED package is
present, so they fall to the same mutation as the three obvious ones:

    never follow a borrowing                       -> 6 red: the sibling, the loose module, the
                                                      transitive chain, the cycle, the dotted
                                                      import, and the live bot's own borrowing
    count a relative import as a top-level name    -> 1 red: the relative-import case
    take the whole dotted name, not its head       -> 1 red: the dotted-import case
    scan `tests/` as well                          -> 1 red: the tests-are-not-scanned case
    swallow a SyntaxError and carry on             -> 1 red: the unparseable file
    return [] for an unknown package               -> 1 red: the unknown package
    drop the visited set                           -> the cycle case HANGS

⚠ **The last one is the only mutation here whose failure is not a red test, so it was MEASURED
rather than read off a summary line**: under a 20-second alarm the run died with exit 142
(SIGALRM) having used the whole 20s, against a 0.2s baseline. **A killed run prints nothing, and
nothing is also what a command that failed instantly prints** — this repo's own rule about probes
whose negative result a healthy system can produce, met in a test harness.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

import package_deps as pd  # noqa: E402


def _pkg(root: Path, name: str, body: str = "") -> Path:
    """A synthetic strategy package, importable by bare name from `root`."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text(body, encoding="utf-8")
    return d


def _names(root: Path, package: str) -> set[str]:
    return {p.rsplit("/", 1)[-1] for p in pd.local_dependencies(package, root=root)}


# ── the closure ───────────────────────────────────────────────────────────────
def test_a_package_that_borrows_NOTHING_is_just_itself(tmp_path):
    _pkg(tmp_path, "alone", "X = 1\n")
    assert _names(tmp_path, "alone") == {"alone"}


def test_a_borrowed_SIBLING_PACKAGE_comes_too(tmp_path):
    """🔴 The bug itself. MUTATION: return only the package and this goes red.

    This is what `b_leg` and `extreme_leg` do to `sos_fade`, and copying one directory left the
    borrowed half out of the snapshot entirely."""
    _pkg(tmp_path, "lender", "Y = 2\n")
    _pkg(tmp_path, "borrower", "from lender import Y\n")
    assert _names(tmp_path, "borrower") == {"borrower", "lender"}


def test_a_borrowed_LOOSE_MODULE_comes_too(tmp_path):
    """The shared live contract's shape — a single `.py` beside the packages, not a directory.
    It is the half a directory-only rule silently drops."""
    (tmp_path / "shared_thing.py").write_text("Z = 3\n", encoding="utf-8")
    _pkg(tmp_path, "borrower", "from shared_thing import Z\n")
    assert _names(tmp_path, "borrower") == {"borrower", "shared_thing.py"}


def test_a_borrowing_of_a_borrowing_comes_too(tmp_path):
    """Transitive, because the live bot's own chain is one: a bot borrows `sos_fade`, which
    borrows `loss_recovery`. Stopping at one level leaves the snapshot one package short."""
    _pkg(tmp_path, "c", "W = 3\n")
    _pkg(tmp_path, "b", "from c import W\n")
    _pkg(tmp_path, "a", "from b import W\n")
    assert _names(tmp_path, "a") == {"a", "b", "c"}


def test_two_packages_borrowing_each_other_TERMINATES(tmp_path):
    """MUTATION: drop the visited set and this never returns. Written so a hang fails the suite
    on its timeout rather than passing quietly."""
    _pkg(tmp_path, "ping", "import pong\n")
    _pkg(tmp_path, "pong", "import ping\n")
    assert _names(tmp_path, "ping") == {"ping", "pong"}


# ── what must NOT widen the answer ────────────────────────────────────────────
def test_a_RELATIVE_import_adds_nothing(tmp_path):
    """`from .execution import x` is internal. MUTATION: ignore the import level and this reddens
    — a package with an internal module sharing a sibling's name would drag that sibling in."""
    _pkg(tmp_path, "lender", "Y = 2\n")
    borrower = _pkg(tmp_path, "borrower", "from .lender import Y\n")
    (borrower / "lender.py").write_text("Y = 9\n", encoding="utf-8")
    assert _names(tmp_path, "borrower") == {"borrower"}


def test_a_DOTTED_import_contributes_only_its_head(tmp_path):
    """`from lender.deep.part import x` needs `lender`, which is what the bare-name path resolves.
    MUTATION: keep the whole dotted name and nothing resolves, so the sibling is dropped."""
    lender = _pkg(tmp_path, "lender")
    (lender / "deep.py").write_text("Y = 2\n", encoding="utf-8")
    _pkg(tmp_path, "borrower", "from lender.deep import Y\n")
    assert _names(tmp_path, "borrower") == {"borrower", "lender"}


def test_a_name_that_is_not_LOCAL_is_ignored(tmp_path):
    """Engines, the backtest package and the standard library all resolve elsewhere, and the
    caller copies those trees wholesale. Answering about them here would be a second opinion."""
    _pkg(tmp_path, "borrower", "import json\nfrom market_structure import Bar\n")
    assert _names(tmp_path, "borrower") == {"borrower"}


def test_a_TESTS_folder_cannot_widen_the_snapshot(tmp_path):
    """🔴 The scan covers exactly the files a snapshot HOLDS, and `tests/` is not copied.

    MUTATION: scan skipped directories too and this reddens. A test's imports pulling a package
    into a live bot's deployment is the fixture-more-capable-than-production trap pointed at the
    money path."""
    _pkg(tmp_path, "lender", "Y = 2\n")
    borrower = _pkg(tmp_path, "borrower")
    tests = borrower / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text("from lender import Y\n", encoding="utf-8")
    assert _names(tmp_path, "borrower") == {"borrower"}


# ── it refuses rather than answering partially ────────────────────────────────
def test_a_file_that_will_not_PARSE_refuses_and_names_it(tmp_path):
    """🔴 Rule 1 on the money path: *nothing to add* and *could not look* must not be one answer.

    A partial closure builds a snapshot that does not import — the defect this replaced, except
    discovered later by a bot that will not start. MUTATION: swallow the SyntaxError and this
    goes red."""
    _pkg(tmp_path, "broken", "def (:\n")
    with pytest.raises(pd.UnreadablePackage) as exc:
        pd.local_dependencies("broken", root=tmp_path)
    assert "broken" in str(exc.value)


def test_a_package_that_does_not_EXIST_refuses(tmp_path):
    """MUTATION: return `[]` and this reddens. A promote for a package nobody can find must stop,
    not quietly copy the shared trees and call it a deployment."""
    with pytest.raises(pd.UnreadablePackage):
        pd.local_dependencies("no_such_package", root=tmp_path)


def test_NO_package_named_is_nothing_to_do_rather_than_an_error(tmp_path):
    """A bot with no strategy package configured. Distinct from the case above: one is a blank
    field, the other is a name that does not resolve."""
    assert pd.local_dependencies("", root=tmp_path) == []


# ── the shape the callers depend on ───────────────────────────────────────────
def test_the_answer_is_SORTED(tmp_path):
    """Both callers turn this into an ordered list — a snapshot's files and a version's git
    pathspecs — and an unstable order makes both irreproducible."""
    for name in ("zeta", "alpha", "mid"):
        _pkg(tmp_path, name, "V = 1\n")
    _pkg(tmp_path, "borrower", "import zeta\nimport alpha\nimport mid\n")
    got = pd.local_dependencies("borrower", root=tmp_path)
    assert got == sorted(got)


def test_a_FILE_root_yields_itself(tmp_path):
    """`snapshot_sources` is what lets a loose module be carried like a one-file tree, so the
    copier needs no special case for it."""
    mod = tmp_path / "solo.py"
    mod.write_text("A = 1\n", encoding="utf-8")
    assert [rel.name for _, rel in pd.snapshot_sources(mod)] == ["solo.py"]


# ── against the real repo ─────────────────────────────────────────────────────
def test_the_LIVE_bot_borrows_a_package_of_its_own(tmp_path):
    """🔴 Measured, not hypothetical: `sos_fade` imports `loss_recovery`, and the live bot's
    deployed snapshot does not contain it.

    It is a LAZY import inside a method nothing on the live path calls, so it has never fired —
    but the snapshot has been one package short of its own code for as long as that import has
    existed, and the pin could not tell. MUTATION: return only the package and this reddens."""
    got = pd.local_dependencies("sos_fade")
    assert "strategies/python/sos_fade" in got
    assert "strategies/python/loss_recovery" in got
