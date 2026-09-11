"""Plant a bug IN MEMORY, run only the tests that cover it, and say whether they caught it.

    python -m scripts.testing.mutate FILE 'exact old text' 'new text'
    python -m scripts.testing.mutate FILE 'old' 'new' -- tests/test_x.py -k name
    python -m scripts.testing.mutate FILE 'old' 'new' --in command-center/backend -- tests/...

Exit 0 = the tests went RED (the mutation was killed - the tests can see this code).
Exit 1 = they stayed GREEN (it survived - nothing is checking that line).
Exit 2 = the mutation could not be planted (text absent or not unique) - nothing was run.

🔴 **Nothing on disk changes.** Rule 12 is proven by planting a bug and watching a test go red, and
the obvious way to plant one is to edit the file - in a clone two sessions share, where the other
session's run or commit can pick the planted bug up, and a crash mid-loop leaves it behind. Here the
mutated source is served to Python's import system instead: a `sitecustomize` on PYTHONPATH swaps
the compiled code for that one file, in the pytest process AND every Python process it starts
(xdist workers, gate scripts run by subprocess), and disappears when the run ends.

⚠ **Python only.** A node check or a browser spec does not see the planted bug - it will read as
SURVIVED. ⚠ The covering tests default to the fast tier's own selection for FILE; pass `--` and
your own pytest arguments to narrow them. ⚠ A survivor is a question, not an answer: read whether
any test was ever meant to see that line before writing a test for it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import manifest, rules
from .fast import build_graph
from .selection import select
from .vps_guard import HOOKS

REPO = rules.REPO


def _pytest_loads_it_itself(target: Path) -> bool:
    """pytest imports test modules and conftest files through its own assertion rewriter, which
    reads the file from DISK - so a bug planted in memory never reaches the run."""
    name = target.name
    return name == "conftest.py" or (
        name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))
    )


def plant(target: Path, old: str, new: str) -> str:
    # 🔴 REFUSED, never run: planted here it reported SURVIVED for two bugs that a real plant
    # (in a throwaway worktree) showed the tests DID catch - a false survivor, 2026-09-10.
    if _pytest_loads_it_itself(target):
        raise ValueError(
            f"{target.name} is a test module or conftest - pytest reads it from disk, so a bug "
            "planted in memory never runs. Plant it in the code under test, or edit a copy in a "
            "throwaway worktree (git worktree add)"
        )
    src = target.read_text(encoding="utf-8")
    n = src.count(old)
    if n != 1:
        raise ValueError(f"the old text occurs {n} times in {target} - it must occur exactly once")
    return src.replace(old, new)


def covering_tests(target: Path) -> dict:
    """{suite: [test files]} the fast tier would run for a change to `target`."""
    rel = target.relative_to(REPO).as_posix()
    graph = build_graph(manifest.current())
    sel = select(graph, rules, {rel: "modified"})
    return {name: sorted(tests) for name, tests in sel.tests.items() if tests}


def run(target: Path, old: str, new: str, pytest_args=None, cwd=None) -> int:
    """`cwd` (repo-relative) is where explicit `pytest_args` run - the backend suite must run from
    its own folder, where its pytest.ini carries the live-VPS interlock."""
    target = target.resolve()
    try:
        mutated = plant(target, old, new)
    except (OSError, ValueError) as exc:
        print(f"could not plant: {exc}")
        return 2
    if pytest_args:
        groups = {cwd or "": list(pytest_args)}
    else:
        groups = {}
        for suite in rules.SUITES:
            files = covering_tests(target).get(suite.name, [])
            if files:
                cwd = REPO / suite.root if suite.root else REPO
                groups[suite.root] = [os.path.relpath(REPO / f, cwd) for f in files]
    if not groups:
        print("no test reaches this file - nothing could catch the mutation (SURVIVED)")
        return 1
    with tempfile.TemporaryDirectory(prefix="lwg-mutation-") as tmp:
        spec = Path(tmp) / "mutation.json"
        spec.write_text(json.dumps({"target": os.path.realpath(target), "source": mutated}))
        # The ONE shared start-up hook (child_hooks/sitecustomize.py) serves the planted source.
        # ⚠ Never a second sitecustomize: Python imports only the first on the path, so a second
        # one would silently shadow the live-VPS guard or be shadowed by it.
        env = dict(os.environ, LWG_MUTATION=str(spec), PYTHONDONTWRITEBYTECODE="1")
        parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and p != str(HOOKS)]
        env["PYTHONPATH"] = os.pathsep.join([str(HOOKS), *parts])
        red = False
        for root, args in groups.items():
            cwd = REPO / root if root else REPO
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=line",
                "-x",
                "-p",
                "no:cacheprovider",
            ]
            proc = subprocess.run(cmd + args, cwd=str(cwd), env=env, capture_output=True, text=True)
            lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
            if proc.returncode == 1:
                red = True
                print(f"KILLED - {lines[-1].strip('= ') if lines else 'red'}")
                for ln in lines:
                    if ln.startswith(("FAILED", "ERROR")) or ln.startswith("/"):
                        print(f"  {ln}")
                break
            if proc.returncode not in (0, 5):
                print(f"pytest could not run (exit {proc.returncode}):")
                print("\n".join(lines[-15:]))
                return 2
    if not red:
        print("SURVIVED - every covering test stayed green with the bug planted")
        return 1
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra, cwd = None, None
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1 :]
    if "--in" in argv:
        i = argv.index("--in")
        cwd = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i : i + 2]
    if len(argv) != 3:
        print(__doc__)
        return 2
    return run(Path(argv[0]), argv[1], argv[2], extra, cwd)


if __name__ == "__main__":
    raise SystemExit(main())
