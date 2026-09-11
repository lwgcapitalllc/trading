"""This repo's half of the fast test tier - concrete where `graph.py` is generic.

Everything the selector needs to know about THIS repo lives here: where a bare import resolves,
which pytest suites exist, which step of `scripts/run_all_tests.sh` reads which files, and what a
changed non-Python file means.

⚠ **The step numbers are `run_all_tests.sh`'s own.** `tests/test_rules.py` goes red when that
script gains, loses or renumbers a step this file does not know about, because a step the fast
tier has never heard of is a check that silently stops running on every everyday change.

⚠ **When in doubt this file must over-select.** A file nothing here can map, sitting in a code
tree, runs EVERYTHING (`CODE_TREES`). The full run's blind-spot report (`stamp.py`) is what
finds a rule that is missing here - read it when it speaks.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from .graph import Suite

REPO = Path(__file__).resolve().parents[2]

# Every directory a bare import can resolve from. MEASURED 2026-09-10: with these, every
# local-looking import in the repo resolved. They are the directories the code puts on sys.path
# itself (`sys.path.insert` in 275 files - evaluating those calls is not worth it; this fixed
# union covers them). The importing file's own directory is always searched as well.
SEARCH_ROOTS = (
    "",
    "engines",
    "command-center/backend",
    "strategies/python",
    "algos/live",
    "algos/shared",
    "algos/tools",
    "algos/notifications",
    "algos/bots",
    "algos/tests",
    "backtest/tests",
    "backtest/tools",
    "strategies/python/sos_fade/tools",
    "engines/market_structure/tests",
    "algos/markets/fx/tools",
    "smart-money",
)

SUITES = (
    # Step 1. The root pytest.ini's rootdir, and the folders step 1 hands pytest.
    Suite(
        name="root",
        root="",
        dirs=("engines", "backtest", "algos", "strategies", "smart-money", "execution", "scripts"),
        ignore=("algos/nt8/test_bt_switch.py",),  # a VPS debug script, see conftest.py
    ),
    # Step 2. Run from its own folder: its pytest.ini carries the live-VPS interlock.
    Suite(name="backend", root="command-center/backend", dirs=("command-center/backend",)),
)

PY = "{python}"  # replaced with the interpreter the run uses

_FE = "command-center/frontend"
# What the TypeScript program reads (tsconfig includes src only; specs are not in it).
FRONTEND_TS = (
    f"{_FE}/src/*",
    f"{_FE}/tsconfig*.json",
    f"{_FE}/package.json",
    f"{_FE}/package-lock.json",
    f"{_FE}/vite.config.ts",
)
# The node checks read one module each, and the theme check walks all of src - so any frontend
# source edit runs all five. They cost ~0.2s each, and a per-check input list is one more thing
# to go stale.
FRONTEND_ANY = FRONTEND_TS + (
    f"{_FE}/scripts/*",
    f"{_FE}/tailwind.config.js",
    f"{_FE}/postcss.config.js",
    f"{_FE}/index.html",
    f"{_FE}/tests/fixtures/*",
)


@dataclass(frozen=True)
class Step:
    """One non-pytest step of run_all_tests.sh, and what decides whether a change reaches it."""

    id: int
    name: str
    cmd: tuple
    cwd: str = ""
    script: str = ""  # a Python entry point: it runs when anything it imports changes
    globs: tuple = ()  # files (or whole trees) it reads that no import line names
    heavy: bool = False  # takes every core itself, so it runs in turn with the suites, not beside


def _node(id_, name, script):
    return Step(id_, name, ("node", f"scripts/{script}"), cwd=_FE, globs=FRONTEND_ANY)


# The OFFLINE browser specs - playwright.config.ts discovers them by this same text, and
# tests/test_rules.py holds the two to one marker.
OFFLINE_MARKER = "offlineTest("
_IMPORT = re.compile(
    r"""(?:\b(?:import|export)\b[^'"]*?\bfrom\s*|\bimport\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]""",
    re.M,
)
_TS_EXT = ("", ".ts", ".tsx", ".js", ".jsx", ".mjs", "/index.ts", "/index.tsx")
_APP = f"{_FE}/src/App.tsx"
_BOTS_PAGE = f"{_FE}/src/pages/Bots/"


def offline_specs() -> tuple:
    folder = REPO / _FE / "tests"
    return tuple(
        sorted(
            f"{_FE}/tests/{p.name}"
            for p in folder.glob("*.spec.ts")
            if OFFLINE_MARKER in p.read_text(encoding="utf-8", errors="replace")
        )
    )


def _resolve_ts(spec: str, importer: str):
    if spec.startswith("@/"):
        base = f"{_FE}/src/{spec[2:]}"
    elif spec.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
    else:
        return None  # a package
    for ext in _TS_EXT:
        if (REPO / (base + ext)).is_file():
            return base + ext
    return None


def offline_browser_sources() -> tuple:
    """Every source file the offline specs can run: the specs and what they import, and the app from
    main.tsx down - except App.tsx's routes to OTHER pages, which load on /bots but never render.

    ⚠ That exception is the one place this can be wrong: a page that crashes as it LOADS breaks
    /bots too, and is not followed. The full run carries these specs as its own step, so such a
    miss is named there (BLIND SPOT) rather than lost."""
    todo, seen = [f"{_FE}/src/main.tsx", *offline_specs()], set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            text = (REPO / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spec in _IMPORT.findall(text):
            dep = _resolve_ts(spec, path)
            other_page = (
                dep and dep.startswith(f"{_FE}/src/pages/") and not dep.startswith(_BOTS_PAGE)
            )
            if dep and not (path == _APP and other_page):
                todo.append(dep)
    return tuple(sorted(seen))


STEPS = (
    Step(
        3,
        "frontend typecheck",
        # Incremental: the build info lives in node_modules/.cache (already git-ignored), so a
        # warm run re-checks only what moved. MEASURED 2026-09-10: 14.2s cold, 2.5s warm.
        (
            "npx",
            "--no-install",
            "tsc",
            "--noEmit",
            "--incremental",
            "--tsBuildInfoFile",
            "node_modules/.cache/tsc-noemit.tsbuildinfo",
        ),
        cwd=_FE,
        globs=FRONTEND_TS,
    ),
    Step(
        4,
        "browser guard",
        ("node", ".claude/mcp/check_browser_guard.js"),
        globs=(".claude/mcp/browser_guard.js", ".claude/mcp/check_browser_guard.js"),
    ),
    Step(
        5,
        "trading-box server",
        (PY, ".claude/mcp/check_tradingbox.py"),
        script=".claude/mcp/check_tradingbox.py",
    ),
    Step(
        6,
        "documentation-size guard",
        (PY, ".claude/hooks/check_guard.py"),
        script=".claude/hooks/check_guard.py",
    ),
    Step(7, "lab server", (PY, ".claude/mcp/check_lab.py"), script=".claude/mcp/check_lab.py"),
    _node(8, "trade-overlay geometry", "check_trade_geometry.mjs"),
    _node(9, "parameter-condition evaluator", "check_param_conditions.mjs"),
    _node(10, "period-window rebase", "check_period_window.mjs"),
    _node(11, "instrument search + recents", "check_instrument_search.mjs"),
    _node(12, "theme colour tokens", "check_theme_tokens.mjs"),
    Step(
        13,
        "git-hook bypass guard",
        (PY, ".claude/hooks/check_no_verify.py"),
        script=".claude/hooks/check_no_verify.py",
    ),
    Step(
        14,
        "pine block drift",
        (PY, "scripts/check_pine_blocks.py"),
        script="scripts/check_pine_blocks.py",
        globs=("*.pine",),
    ),
    # 15 is the parity gates: selected per COMPONENT, see gates() below.
    Step(
        16,
        "generated pine harness",
        (PY, "scripts/build_fvg_zone_harness.py", "--check"),
        script="scripts/build_fvg_zone_harness.py",
        globs=("*.pine",),
    ),
    Step(
        17,
        "overlap audit baseline",
        (PY, "backtest/tools/overlap_audit.py", "--check-baseline"),
        script="backtest/tools/overlap_audit.py",
    ),
    Step(
        18,
        "pine export twins",
        (PY, "strategies/tradingview/tools/build_export_twins.py", "--check"),
        script="strategies/tradingview/tools/build_export_twins.py",
        globs=("strategies/tradingview/*",),
    ),
    # Needs nothing running and reaches nothing live (tests/offline.ts). It builds the app, so the
    # build's own inputs count as well as the source the Bots page imports.
    Step(
        19,
        "offline browser specs",
        ("npx", "--no-install", "playwright", "test", "--project=offline", "--reporter=line"),
        cwd=_FE,
        globs=offline_browser_sources()
        + (
            f"{_FE}/tests/offline*.ts",
            f"{_FE}/tests/recordings/*",
            f"{_FE}/playwright.config.ts",
            f"{_FE}/index.html",
            f"{_FE}/vite.config.ts",
            f"{_FE}/tailwind.config.js",
            f"{_FE}/postcss.config.js",
            f"{_FE}/tsconfig*.json",
            f"{_FE}/package.json",
            f"{_FE}/package-lock.json",
            f"{_FE}/src/themes/*",
            f"{_FE}/public/*",
        ),
        heavy=True,
    ),
)
GATE_STEP = 15
GATE_RUNNER = "scripts/check_engine_gates.py"  # a change reaching the runner runs every gate
PYTEST_STEPS = {1: "root", 2: "backend"}


@dataclass(frozen=True)
class Action:
    """What a changed file matching a TABLE glob means, on top of (or instead of) the generic rules."""

    note: str = ""  # said to the reader
    readers: bool = True  # still seed Python files whose strings name the file
    by_name: bool = True  # ...by its basename too, not only its full path
    package: bool = True  # still seed the package that contains it
    tests: tuple = ()  # these test files run too
    suites: tuple = ()  # every test in these suites runs
    gate: bool = False  # a golden export: run its own component's parity gate
    escalate: str = ""  # run everything, for this reason


_BROWSER = Action(
    note="a browser check - the OFFLINE specs run here (step 19); one on the real backend is yours "
    "to run with the app up",
    readers=False,
    package=False,
)

TABLE = (
    # A golden export feeds its own gate, the runner's test, and any test naming the file. Not the
    # package: a golden CSV is under an engine package, and "every importer of the engine" is 180
    # test files for a file only one gate reads.
    (
        "*/exports/golden/*",
        Action(gate=True, package=False, tests=("engines/tests/test_golden_runner.py",)),
    ),
    (f"{_FE}/tests/*.spec.ts", _BROWSER),
    (f"{_FE}/tests/fixtures.ts", _BROWSER),
    # The offline harness: offline.ts, the build it serves (offlineApp.ts) and its setup/teardown.
    (f"{_FE}/tests/offline*.ts", _BROWSER),
    # A recording a browser spec replays is ALSO read by the backend check that holds it to its
    # route's response model - the one reader a string search cannot find (it globs the folder).
    (
        f"{_FE}/tests/recordings/*",
        Action(
            note=_BROWSER.note,
            readers=False,
            package=False,
            tests=("command-center/backend/tests/test_api_recordings.py",),
        ),
    ),
    (
        f"{_FE}/scripts/record-api.mjs",
        Action(note="the recorder a person runs", readers=False, package=False),
    ),
    (f"{_FE}/playwright.config.ts", _BROWSER),
    ("pytest.ini", Action(suites=("root",))),
    ("command-center/backend/pytest.ini", Action(suites=("backend",))),
    ("*requirements*.txt", Action(escalate="the packages every suite runs on may have moved")),
    ("scripts/run_all_tests.sh", Action(note="the full runner itself - only a full run uses it")),
    ("scripts/test.sh", Action(note="the fast runner's wrapper")),
    (".githooks/*", Action(note="a git hook - a commit or push exercises it")),
    # A doc is read by path or not at all: "CLAUDE.md" as a bare name appears in dozens of
    # strings that build throwaway repos. The size guard's check names its two real fixtures by
    # path, so a change to either still reaches step 6.
    ("*.md", Action(by_name=False, package=False)),
)

# Nothing here needs a test and nothing reads them; silence is the right answer.
INERT = (
    "*.md",
    "*docs/*",
    "education/*",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.webp",
    "*.pdf",
    ".claude/commands/*",
    ".claude/skills/*",
    ".claude/settings*.json",
    "*/ledger/*",
    ".mcp.json",
    ".gitattributes",
    ".gitignore",
    ".prettierrc.json",
    ".prettierignore",
    "ruff.toml",
    "eslint.config.mjs",
    "lint-staged.config.mjs",
    "package.json",
    "package-lock.json",
)

# A file under one of these that nothing above maps is a file the selector does not understand,
# and not understanding a file in a code tree means running everything.
CODE_TREES = (
    "engines/",
    "backtest/",
    "algos/",
    "strategies/",
    "smart-money/",
    "command-center/",
    "execution/",
    "scripts/",
    ".claude/",
    ".githooks/",
    "indicators/",
)


def matches(path: str, globs) -> bool:
    return any(fnmatch.fnmatchcase(path, g) for g in globs)


def _gate_runner():
    spec = importlib.util.spec_from_file_location(
        "_check_engine_gates", REPO / "scripts" / "check_engine_gates.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gates():
    """[(component dir, gate script)] for every golden export, repo-relative - the gate runner's
    own discovery, so this list cannot drift from what step 15 runs."""
    out, seen = [], set()
    for component, gate, _csv, _warmup, _extra in _gate_runner()._discover():
        rel = component.relative_to(REPO).as_posix()
        if rel in seen or gate is None:
            continue
        seen.add(rel)
        out.append((rel, gate.relative_to(REPO).as_posix()))
    return out


def component_of_golden(path: str) -> str:
    """engines/vwap/exports/golden/x.csv -> engines/vwap"""
    head = path.split("/exports/golden/", 1)[0]
    return posixpath.normpath(head)
