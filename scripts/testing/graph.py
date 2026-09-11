"""A static import graph over the repo's Python source, and the tests a change can reach.

Generic on purpose: nothing in this file knows the repo's layout. `rules.py` hands it the search
roots, the suites and the file tables; this file reads source and walks edges.

WHY STATIC, NOT COVERAGE-TRACED
- A coverage-traced selector (pytest-testmon) is not installed, pays a full traced run up front, and
  is blind to exactly the inputs this repo keeps paying for: data files (golden exports, meta.json,
  Pine), files read as TEXT, subprocesses and git history.
- A static graph is deterministic, costs well under a second, and can say WHY it picked a test.
  It is per FILE, so a hub (the replay stack imports every engine) selects broadly. That is the
  honest price: over-selecting costs seconds, under-selecting costs a red suite on main.

THE RULES (each one closes a real way a test reaches code without a plain import line)
1. every import in a file counts, including one inside a function - a lazy import is still a
   dependency
2. importlib / __import__ with a literal name; with an f-string, every package one level under
   its fixed prefix (the backend loads strategies as `strategies.python.{pkg}`)
3. a dotted string literal that resolves to a module (a mock.patch target)
4. a string literal naming a .py file (a script loaded or run by path)
5. conftest: a module-level import reaches every test beneath it; an import inside a FIXTURE
   reaches only the tests that use that fixture or one built on it. Without this the backend's
   lazy `import main` in one fixture selects every backend test for any change at all.
6. a changed NON-python file seeds every .py whose strings name it or glob-match it, and the
   package that contains it
"""

from __future__ import annotations

import ast
import fnmatch
import os
import pickle
import posixpath
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

_DOTTED = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
_SPLIT = re.compile(r"[/\\\s\"'`,;:()\[\]{}=]+")
_GLOB = re.compile(r"[A-Za-z0-9_.\-*]+")
# Strings longer than this are prose (an error message, a help text), not a name.
_MAX_LITERAL = 300
# A suffix check like `.endswith(".json")` says nothing about WHICH file a code path reads, so
# these generic suffixes are not treated as naming a changed file. Specific suffixes (".pine",
# ".meta.json") still are.
_GENERIC_SUFFIXES = {".json", ".py", ".md", ".txt", ".csv", ".log", ".jsonl", ".js", ".ts", ".sh"}
_IMPORT_FUNCS = {"import_module", "__import__"}
_MAX_NAMESAKES = 3  # a bare "x.py" literal names a file only if at most this many share the name


@dataclass
class Facts:
    """What one Python file says about its dependencies, read off its syntax tree."""

    imports: list = field(default_factory=list)  # (dotted, level, names) outside any fixture
    fixture_imports: dict = field(default_factory=dict)  # conftest fixture -> [imports]
    fixture_params: dict = field(default_factory=dict)  # conftest fixture -> {param names}
    autouse: set = field(default_factory=set)  # conftest fixtures that apply to every test
    prefixes: list = field(default_factory=list)  # f-string import prefixes
    strings: list = field(default_factory=list)  # string literals, docstrings excluded
    tokens: set = field(default_factory=set)  # path components of every string
    globs: list = field(default_factory=list)  # last segment of every glob-like string
    suffixes: list = field(default_factory=list)  # ".x" suffix strings, generic ones dropped
    names: set = field(default_factory=set)  # every argument name + short string (fixture use)
    parse_error: str = ""


def is_conftest(path: str) -> bool:
    return posixpath.basename(path) == "conftest.py"


_SCOPES = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _docstring_of(node):
    body = getattr(node, "body", None)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            return id(body[0].value)
    return None


def _decorator_calls(node):
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        yield name, dec


def _fixture_info(node):
    """(fixture name, autouse) if `node` is a pytest fixture definition, else None."""
    for name, dec in _decorator_calls(node):
        if name != "fixture":
            continue
        fixture_name, autouse = node.name, False
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    fixture_name = str(kw.value.value)
                if kw.arg == "autouse" and isinstance(kw.value, ast.Constant):
                    autouse = bool(kw.value.value)
        return fixture_name, autouse
    return None


def _arg_names(args: ast.arguments):
    for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
        yield a.arg
    if args.vararg:
        yield args.vararg.arg
    if args.kwarg:
        yield args.kwarg.arg


def _imports_of(node):
    if isinstance(node, ast.Import):
        return [(a.name, 0, ()) for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [(node.module or "", node.level or 0, tuple(a.name for a in node.names))]
    return None


def _dynamic_import(node):
    """('name', dotted) or ('prefix', dotted.) for importlib calls, else None."""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = node.func
    fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if fname not in _IMPORT_FUNCS:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return "name", arg.value
    if isinstance(arg, ast.JoinedStr) and arg.values:
        first = arg.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return "prefix", first.value
    return None


def parse(source: str, *, conftest: bool = False) -> Facts:
    facts = Facts()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        facts.parse_error = str(exc)
        return facts
    # ONE walk. ast.walk is breadth-first, so a scope is always visited before its docstring,
    # which lets the docstring set fill in as the walk goes.
    docstrings = set()

    owner_of = {}  # id(node) -> conftest fixture whose body holds it
    if conftest:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                info = _fixture_info(node)
                if not info:
                    continue
                name, autouse = info
                facts.fixture_params[name] = set(_arg_names(node.args))
                facts.fixture_imports.setdefault(name, [])
                if autouse:
                    facts.autouse.add(name)
                for sub in ast.walk(node):
                    owner_of[id(sub)] = name

    for node in ast.walk(tree):
        if isinstance(node, _SCOPES):
            doc = _docstring_of(node)
            if doc is not None:
                docstrings.add(doc)
        owner = owner_of.get(id(node))
        bucket = facts.fixture_imports[owner] if owner else facts.imports
        imps = _imports_of(node)
        if imps:
            bucket.extend(imps)
            continue
        dyn = _dynamic_import(node)
        if dyn:
            kind, value = dyn
            if kind == "name":
                bucket.append((value, 0, ()))
            else:
                facts.prefixes.append(value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            facts.names.update(_arg_names(node.args))
        # Only a string with no whitespace can be a path, a module or a glob. "see App.tsx" is a
        # SENTENCE (an error message), and reading it as a reference made a frontend edit select
        # the whole backend.
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and len(node.value) <= _MAX_LITERAL
            and not any(c.isspace() for c in node.value)
        ):
            s = node.value
            facts.strings.append(s)
            if s.isidentifier():
                facts.names.add(s)  # usefixtures("x"), getfixturevalue("x")
            facts.tokens.update(t for t in _SPLIT.split(s) if t)
            tail = s.rsplit("/", 1)[-1]
            # "*.json" alone names no file: it reads whatever sits in ITS directory, which a bare
            # tail cannot say. Specific globs ("compare_*.py", "*.meta.json") are kept.
            # And only a PLAIN file pattern: "[.\\-_A-Za-z0-9]*" is a regex, and fnmatch reads its
            # bracket as a character class that matches every file in the repo.
            generic = tail.startswith("*.") and tail[1:] in _GENERIC_SUFFIXES
            plain = _GLOB.fullmatch(tail) and len(tail.replace("*", "")) >= 2
            if "*" in tail and plain and not generic:
                facts.globs.append(tail)
            if (
                s.startswith(".")
                and len(s) > 2
                and "/" not in s
                and " " not in s
                and s not in _GENERIC_SUFFIXES
            ):
                facts.suffixes.append(s)
    return facts


@dataclass
class Suite:
    """One pytest invocation: where it runs from and which files it collects."""

    name: str
    root: str  # the directory pytest runs in (its rootdir); "" = repo root
    dirs: tuple  # test files under these directories belong to this suite
    ignore: tuple = ()

    def owns(self, path: str) -> bool:
        base = posixpath.basename(path)
        if not base.endswith(".py") or not (base.startswith("test_") or base.endswith("_test.py")):
            return False
        if path in self.ignore:
            return False
        return any(path.startswith(d + "/") for d in self.dirs)


_CACHE_VERSION = 4  # bump whenever parse() changes what it extracts


def load_facts(tree: dict, read, cache_path=None) -> dict:
    """{path: Facts} for every .py in `tree` ({path: content hash}).

    Parsing is the whole cost of building the graph (~4s cold for ~600 files), so facts are cached
    by CONTENT HASH: a file is re-parsed exactly when its bytes changed, and never otherwise.
    """
    cached = {}
    if cache_path is not None:
        try:
            with open(cache_path, "rb") as fh:
                blob = pickle.load(fh)
            if blob.get("version") == _CACHE_VERSION:
                cached = blob["facts"]
        except (OSError, EOFError, pickle.PickleError, AttributeError, KeyError, TypeError):
            cached = {}
    out, fresh = {}, 0
    for path, digest in tree.items():
        if not path.endswith(".py"):
            continue
        hit = cached.get(path)
        if hit and hit[0] == digest:
            out[path] = hit[1]
            continue
        out[path] = parse(read(path) or "", conftest=is_conftest(path))
        fresh += 1
    if cache_path is not None and fresh:
        tmp = f"{cache_path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "wb") as fh:
                pickle.dump(
                    {"version": _CACHE_VERSION, "facts": {p: (tree[p], f) for p, f in out.items()}},
                    fh,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
            os.replace(tmp, cache_path)  # two sessions share this cache
        except OSError:
            pass  # a cache that cannot be written only costs the next run its speed
    return out


class Graph:
    """Dependency edges between the repo's Python files, and the walk back from a change."""

    def __init__(self, files, facts: dict, search_roots):
        self.files = set(files)
        self.roots = tuple(search_roots)
        self.py = sorted(p for p in self.files if p.endswith(".py"))
        self.facts = {p: facts.get(p) or Facts() for p in self.py}
        self.by_base = defaultdict(set)
        for p in self.py:
            self.by_base[posixpath.basename(p)].add(p)
        self.by_module = defaultdict(set)
        for p in self.py:
            for mod in self.module_names(p):
                self.by_module[mod].add(p)
        self.deps = {}  # file -> files it depends on (fixture imports excluded)
        self.fixture_deps = {}  # (conftest, fixture) -> files that fixture imports
        self.rdeps = defaultdict(set)
        for p in self.py:
            f = self.facts[p]
            deps = set()
            for imp in f.imports:
                deps |= self._resolve(p, *imp)
            for prefix in f.prefixes:
                deps |= self._prefix_modules(prefix)
            for s in f.strings:
                if s.endswith(".py") and "\n" not in s and " " not in s:
                    deps |= self._py_named(s)
                elif _DOTTED.match(s):
                    deps |= self._dotted_string(s)
            deps.discard(p)
            self.deps[p] = deps
            for d in deps:
                self.rdeps[d].add(p)
            for fixture, imps in f.fixture_imports.items():
                fdeps = set()
                for imp in imps:
                    fdeps |= self._resolve(p, *imp)
                self.fixture_deps[(p, fixture)] = fdeps
                for d in fdeps:
                    self.rdeps[d].add((p, fixture))

    # ── names ──────────────────────────────────────────────────────────────────────────────

    def module_names(self, path: str) -> set:
        """Every dotted name `path` is importable as, one per search root it sits under."""
        out = set()
        for root in self.roots:
            if root and not path.startswith(root + "/"):
                continue
            rel = path[len(root) + 1 :] if root else path
            mod = rel[:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[: -len(".__init__")]
            elif mod == "__init__":
                continue
            out.add(mod)
        return out

    def _existing(self, stem: str) -> set:
        return {c for c in (stem + ".py", stem + "/__init__.py") if c in self.files}

    def _resolve(self, src, dotted, level, names) -> set:
        out = set()
        if level:
            base = posixpath.dirname(src)
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            stem = posixpath.join(base, *dotted.split(".")) if dotted else base
            out |= self._existing(stem)
            for n in names:
                if n != "*":
                    out |= self._existing(posixpath.join(stem, n))
            return out
        if not dotted:
            return out
        parts = dotted.split(".")
        mods = [dotted] + [".".join(parts[:i]) for i in range(1, len(parts))]
        mods += [f"{dotted}.{n}" for n in names if n != "*"]
        for m in mods:
            out |= self.by_module.get(m, set())
        own = posixpath.dirname(src)  # a sibling import after inserting the file's own dir
        for m in mods:
            out |= self._existing(
                posixpath.join(own, *m.split(".")) if own else m.replace(".", "/")
            )
        return out

    def _prefix_modules(self, prefix: str) -> set:
        """Packages one level under an f-string import prefix, e.g. strategies.python.{pkg}."""
        head = prefix if prefix.endswith(".") else prefix + "."
        out = set()
        for mod, paths in self.by_module.items():
            if mod.startswith(head) and "." not in mod[len(head) :]:
                out |= paths
        return out

    def _dotted_string(self, s: str) -> set:
        parts = s.split(".")
        for i in range(len(parts), 1, -1):
            hit = self.by_module.get(".".join(parts[:i]))
            if hit:
                return set(hit)
        return set()

    def _py_named(self, s: str) -> set:
        # Strip a leading "./" or "/" only - never a leading dot, or ".claude/..." loses its dot.
        while s.startswith("./"):
            s = s[2:]
        s = s.lstrip("/")
        if "/" in s:
            return {p for p in self.py if p == s or p.endswith("/" + s)}
        # A bare name shared by many files ("__init__.py", "config.py") is a scanner walking a
        # tree, not a reference to any one of them - matching all 60 would make every package's
        # init reach every importer of that scanner.
        hits = self.by_base.get(s, set())
        return set(hits) if len(hits) <= _MAX_NAMESAKES else set()

    # ── non-python files ───────────────────────────────────────────────────────────────────

    def readers(self, path: str, *, by_name: bool = True, globs: bool = True) -> set:
        """Python files whose string literals name `path` - by path, by basename, by glob.

        `by_name=False` matches the full path only: a name as common as CLAUDE.md appears in
        dozens of strings that build throwaway repos and read no real file.
        """
        base = posixpath.basename(path)
        has_dir = "/" in path
        out = set()
        for p in self.py:
            f = self.facts[p]
            if by_name and base in f.tokens:
                out.add(p)
                continue
            if has_dir and any(path in s for s in f.strings):
                out.add(p)
                continue
            if by_name and any(base.endswith(sfx) for sfx in f.suffixes):
                out.add(p)
                continue
            if by_name and globs and any(fnmatch.fnmatchcase(base, g) for g in f.globs):
                out.add(p)
        return out

    def package_of(self, path: str):
        d = posixpath.dirname(path)
        while d:
            init = d + "/__init__.py"
            if init in self.files:
                return init
            d = posixpath.dirname(d)
        return None

    def importers_of_deleted(self, path: str) -> set:
        """Files still importing a module that no longer exists - they will fail to import."""
        names = self.module_names(path)
        stem = path[: -len("/__init__.py")] if path.endswith("/__init__.py") else path[:-3]
        out = set()
        for p in self.py:
            f = self.facts[p]
            imps = list(f.imports) + [i for v in f.fixture_imports.values() for i in v]
            for dotted, level, fromnames in imps:
                if level:
                    base = posixpath.dirname(p)
                    for _ in range(level - 1):
                        base = posixpath.dirname(base)
                    target = posixpath.join(base, *dotted.split(".")) if dotted else base
                    cands = {target} | {posixpath.join(target, n) for n in fromnames}
                    if stem in cands:
                        out.add(p)
                    continue
                mods = {dotted} | {f"{dotted}.{n}" for n in fromnames}
                if mods & names:
                    out.add(p)
        return out

    # ── the walk ───────────────────────────────────────────────────────────────────────────

    def reach(self, seeds) -> dict:
        """Every node that transitively depends on a seed, mapped to the node it was reached from.

        Nodes are file paths and (conftest, fixture) pairs. A seed maps to None.
        """
        came_from = {s: None for s in seeds}
        queue = deque(seeds)
        while queue:
            x = queue.popleft()
            for y in self.rdeps.get(x, ()):
                if y not in came_from:
                    came_from[y] = x
                    queue.append(y)
        return came_from

    def conftests_of(self, test: str, suite_root: str) -> list:
        out = []
        d = posixpath.dirname(test)
        while True:
            c = posixpath.join(d, "conftest.py") if d else "conftest.py"
            if c in self.files and (not suite_root or c.startswith(suite_root + "/")):
                out.append(c)
            if not d or d == suite_root:
                break
            d = posixpath.dirname(d)
        return out

    def fixtures_used(self, conftest: str, test: str) -> set:
        """The conftest's fixtures a test file uses, closed over fixtures built on fixtures."""
        c = self.facts[conftest]
        known = set(c.fixture_params)
        used = (self.facts[test].names & known) | c.autouse
        frontier = list(used)
        while frontier:
            f = frontier.pop()
            for dep in c.fixture_params.get(f, ()):
                if dep in known and dep not in used:
                    used.add(dep)
                    frontier.append(dep)
        return used

    def tests_reached(self, came_from: dict, suite: Suite) -> dict:
        """{test file: how it was reached} for every test of `suite` a change can reach."""
        out = {}
        for t in self.py:
            if not suite.owns(t):
                continue
            if t in came_from:
                out[t] = t
                continue
            for c in self.conftests_of(t, suite.root):
                if c in came_from:
                    out[t] = c
                    break
                hit = next((f for f in self.fixtures_used(c, t) if (c, f) in came_from), None)
                if hit:
                    out[t] = (c, hit)
                    break
        return out

    def chain(self, came_from: dict, node) -> list:
        """The path from a seed to `node`, seed first - the answer to 'why was this picked?'."""
        out = []
        while node is not None:
            out.append(node)
            node = came_from.get(node)
        return list(reversed(out))
