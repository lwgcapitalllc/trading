"""Which files under `strategies/python/` a strategy package needs in order to run.

**Why this exists.** A strategy package does not stand alone. `extreme_leg` borrows one class
from `sos_fade` and the shared live contract from `live_contract.py`; `b_leg` borrows six things
from `sos_fade` across three files. Both imports are BARE NAMES resolved by a `sys.path.insert`
pointing at this directory, so in the repo they simply work and nothing anywhere records that a
dependency exists.

🔴 **A LIVE BOT DOES NOT RUN FROM THE REPO. It runs from a frozen snapshot, and the snapshot was
built from a list of three trees that had never heard of any of this.** `algos/tools/promote.py`
copied the bot's OWN package plus `engines/` and `backtest/`, so a snapshot for either of those
two bots could not import at all. **Nothing caught it for as long as it existed**: the only bot
anybody has ever promoted is `sos_fade`, which borrows nothing, so every promote that has ever
run was green. It was found on 2026-09-04 by running the promote for the first time — rule 9, a
feature nobody has RUN is not a feature.

**The answer is DERIVED, never declared.** A hand-kept list of "extra trees per bot" is a second
statement of what the code already says, and it goes stale in silence the first time somebody adds
an import — which is the same failure one level up from the one it would be fixing. This walks the
imports instead, so a dependency added tomorrow is picked up by the next promote with nobody
remembering anything.

⚠ **`ast`, never `import`.** This runs on the trading box during a promote. Importing a strategy
package to find out what it imports would execute that package's module-level code on the live
machine, before anything has verified it. Same rule, same reason, as
`command-center/backend/services/bot_versions.setting_changes`.

⚠ **It REFUSES rather than answering partially.** A file that will not parse raises, naming the
file. A partial dependency set builds a snapshot that does not import — which is exactly the
defect this module exists to remove, except silent, and discovered by a bot that will not start.
Never let *nothing to add* and *could not look* be the same answer.

⚠ **The file set scanned is the SAME set a snapshot holds** (`snapshot_sources`), so the thing
that decides what is COPIED and the thing that decides what is NEEDED cannot disagree. A file that
ships in the snapshot must have its imports resolvable there; a file that never ships (a test)
must not be able to widen the snapshot. `algos/tools/promote.py` imports that function rather than
keeping its own copy.

⚠ **Only ABSOLUTE, top-level names count.** A relative import (`from .execution import ...`) is
internal to the package and needs nothing added. A dotted name contributes only its first
component, because that is what the bare-name path resolves.

⚠ **A name is LOCAL only if it exists here** — as a package directory with an `__init__.py`, or
as a loose module file. `market_structure` resolves under `engines/` and `backtest.portfolio`
under `backtest/`, and both of those trees are copied wholesale by the caller, so neither is this
module's business.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Optional, Set, Tuple

__all__ = [
    "PYTHON_ROOT",
    "REPO_REL",
    "SKIP_DIRS",
    "snapshot_sources",
    "local_dependencies",
]

PYTHON_ROOT = Path(__file__).resolve().parent
REPO_REL = "strategies/python"

# Directory names that never belong in a snapshot, at any depth. ⚠ `tools/` is deliberately NOT
# here: a parity harness ships with its strategy, and it imports the same siblings the strategy
# does, so excluding it would narrow the scan without narrowing the copy.
SKIP_DIRS = frozenset({"tests", "__pycache__", ".pytest_cache", ".git"})


class UnreadablePackage(RuntimeError):
    """A file that has to be scanned could not be parsed, so the answer would be incomplete."""


def snapshot_sources(root: Path) -> Iterator[Tuple[Path, Path]]:
    """Every `.py` under `root` that belongs in a snapshot, as (absolute, path relative to root).

    A FILE root yields itself, named by its own filename — that is what lets a loose module here
    be carried like a one-file tree without the caller special-casing it.
    """
    if root.is_file():
        yield root, Path(root.name)
        return
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        if SKIP_DIRS & set(rel.parts):
            continue
        yield py, rel


def _resolve(name: str, root: Path) -> Optional[Path]:
    """The path this bare top-level name refers to under `root`, or None.

    A package directory answers as the DIRECTORY (its whole tree is needed); a loose module
    answers as the FILE. Anything else — a stdlib name, an engine, a third-party package — is not
    local and is not this module's business.

    ⚠ **A directory counts whether or not it holds an `__init__.py`.** Python 3 imports a plain
    directory on the path as a namespace package, so requiring the marker would refuse a
    dependency the interpreter resolves perfectly well — and the cost of the two mistakes is not
    symmetric. An extra directory in a snapshot is dead weight; a missing one is a bot that will
    not start, which is the whole defect this module exists to remove.
    """
    pkg = root / name
    if pkg.is_dir():
        return pkg
    mod = root / f"{name}.py"
    if mod.is_file():
        return mod
    return None


def _imported_names(path: Path) -> Set[str]:
    """The top-level module names this file imports absolutely.

    ⚠ `node.level` is checked because `ImportFrom` covers both `from x import y` (level 0) and
    `from .x import y` (level 1+), and only the first can name a sibling package.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError as exc:  # noqa: B904 — the cause is in the message, and it is the point
        raise UnreadablePackage(
            f"{path} could not be parsed, so which packages it needs cannot be answered: {exc}. "
            f"Fix the file — a snapshot built on a partial answer will not import."
        )
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".", 1)[0])
    return names


def local_dependencies(package: str, root: Optional[Path] = None) -> List[str]:
    """Repo-relative paths under `strategies/python/` that `package` needs, itself included.

    Transitive: a borrowed package's own borrowings come too. Sorted, so a snapshot's file list
    and a version's pathspec list are both reproducible.

    ⚠ **`root` is the `strategies/python/` of the checkout being ASKED ABOUT, and defaults to
    this file's own.** The default is right for every caller today, and it is a parameter because
    the module living in the tree it describes is a coincidence rather than a guarantee — a
    promote resolves `_REPO` from its own location, and a resolver that always answered about
    ITS location would silently describe a different checkout the day those differ.

    Returns `[]` for an empty package name — a bot with no strategy package has nothing to count
    and nothing to copy, and that is the honest answer rather than an error.

    Raises `UnreadablePackage` when a file that must be scanned will not parse, and when the
    named package does not exist here at all — a promote for a package nobody can find must stop,
    not quietly copy `engines/` and `backtest/` and call it a deployment.
    """
    if not package:
        return []
    root = Path(root) if root is not None else PYTHON_ROOT

    start = _resolve(package, root)
    if start is None:
        raise UnreadablePackage(
            f"no strategy package or module named {package!r} under {root} — "
            f"check the bot's configured strategy package."
        )

    found: dict[str, Path] = {package: start}
    queue: List[Path] = [start]
    while queue:
        for src, _ in snapshot_sources(queue.pop()):
            for name in _imported_names(src):
                if name in found:
                    continue
                dep = _resolve(name, root)
                if dep is None:
                    continue
                found[name] = dep
                queue.append(dep)

    return sorted(f"{REPO_REL}/{p.name}" for p in found.values())
