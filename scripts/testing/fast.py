"""The everyday test run: only what the change since the last green run can reach.

    scripts/test.sh              run what changed since the last green run
    scripts/test.sh --explain    print what would run and why, run nothing
    scripts/test.sh --since REF  compare against a git revision instead (e.g. origin/main)
    scripts/test.sh --force      run the selection even if nothing changed
    scripts/test.sh --all        run everything this tier knows (same checks as the full run)

Output is one line per piece plus the failures; everything else goes to .test-logs/fast.log.
⚠ Read the LOG to see a traceback - never re-run an unchanged tree to see output again.

When the full run (scripts/run_all_tests.sh) is required instead: root CLAUDE.md -> *Formatting,
linting and the test gate*.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import manifest, rules
from .graph import Graph, load_facts
from .selection import everything, explain, select

REPO = rules.REPO
LOG = manifest.LOG_DIR / "fast.log"
CPU = os.cpu_count() or 4
_TALLY = re.compile(r"\b\d+ (?:passed|failed|errors?|skipped|deselected)\b.* in [\d.]+s\b")
# Playwright's closing line, e.g. "  98 passed (50.1s)".
_PW_TALLY = re.compile(r"^\s*\d+ passed \(")


def _read(path: str):
    try:
        return (REPO / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def build_graph(tree: dict) -> Graph:
    manifest.LOG_DIR.mkdir(exist_ok=True)
    facts = load_facts(tree, _read, manifest.LOG_DIR / "graph-facts.pickle")
    return Graph(tree.keys(), facts, rules.SEARCH_ROOTS)


class Job:
    """One thing to run, and what it said."""

    def __init__(self, label, cmd, cwd, kind, detail=""):
        self.label, self.cmd, self.cwd, self.kind, self.detail = label, cmd, cwd, kind, detail
        self.code, self.out, self.secs = None, "", 0.0

    def run(self):
        t = time.monotonic()
        try:
            p = subprocess.run(self.cmd, cwd=str(self.cwd), capture_output=True, text=True)
            self.code, self.out = p.returncode, (p.stdout or "") + (p.stderr or "")
        except OSError as exc:
            self.code, self.out = 127, f"could not start {self.cmd[0]}: {exc}"
        self.secs = time.monotonic() - t
        return self

    @property
    def ok(self):
        # pytest exits 5 when every selected test was deselected - the backend's live-VPS suite
        # is deselected by its own pytest.ini, so a selection of only that file is not a failure.
        return self.code == 0 or (self.kind == "pytest" and self.code == 5)


_TEST_DEF = re.compile(r"^\s*(?:async\s+)?def test_", re.M)


def _count_tests(files) -> int:
    """Test functions in these files, before parametrization - a floor, and cheap to read."""
    return sum(len(_TEST_DEF.findall(_read(f) or "")) for f in files)


def _pytest_job(suite, files, python, workers):
    cwd = REPO / suite.root if suite.root else REPO
    rel = sorted(os.path.relpath(REPO / f, cwd) for f in files)
    cmd = [python, "-m", "pytest", "-q", "--tb=short", "-rfE", *rel]
    # Workers follow the number of TESTS, not files: `--dist load` hands out single tests, so two
    # files of 56 git-driven tests spread fine. MEASURED 2026-09-10: those two ran 29s on one core.
    # Each worker costs ~1-2s to start, so a handful of tests stays on one.
    n = min(workers, _count_tests(files) // 12)
    if n > 1:
        cmd[3:3] = ["-n", str(n), "--dist", "load"]
    detail = f"{len(rel)} file{'s' if len(rel) != 1 else ''}"
    return Job(f"{suite.name} pytest", cmd, cwd, "pytest", detail)


def _step_job(step, python):
    cmd = [python if c == rules.PY else c for c in step.cmd]
    return Job(step.name, cmd, REPO / step.cwd if step.cwd else REPO, "step")


def _gates_job(components, python, jobs):
    cmd = [python, "scripts/check_engine_gates.py", "--jobs", str(jobs), "--only"]
    cmd.append(",".join(sorted(components)))
    names = ", ".join(sorted(c.rsplit("/", 1)[-1] for c in components))
    return Job("parity gates", cmd, REPO, "gates", names)


def _summary(job):
    lines = [ln for ln in job.out.splitlines() if ln.strip()]
    if job.kind == "pytest":
        # The TALLY line, found by its shape - never "the last line", which is whatever a library
        # warned about on its way out (urllib3 does, on every run here).
        tallies = [ln.strip("= ").strip() for ln in lines if _TALLY.search(ln)]
        tail = tallies[-1] if tallies else (lines[-1].strip() if lines else "")
        if job.code == 5:
            tail = "no tests to run (all deselected by the suite's own pytest.ini)"
        return tail, [ln for ln in lines if ln.startswith(("FAILED ", "ERROR "))][:20]
    if job.kind == "gates":
        # A gate's own caveats must survive its green (root CLAUDE.md), so a green gate prints only
        # when it carries one, with the caveat under it; a red gate prints whole. The repo-wide
        # COVERAGE lines are the same on every run and stay in the log.
        out, pending = [], None
        for ln in lines:
            s = ln.strip()
            if s.startswith("✓") and ln.startswith("  ✓"):
                pending = ln
            elif ln.startswith("      ") and s.startswith(("⚠", "🔴")):
                if pending:
                    out.append(pending)
                    pending = None
                out.append(ln)
            elif s.startswith(("🔴", "⚠ FILTERED")) or (s.startswith("✓") and "gate(s)" in s):
                out.append(ln)
                pending = None
        return "", out[:40]
    tally = [ln.strip() for ln in lines if _PW_TALLY.match(ln)]
    return (tally[-1] if job.ok and tally else ""), ([] if job.ok else lines[-15:])


def _xdist_missing(python) -> bool:
    p = subprocess.run([python, "-c", "import xdist"], capture_output=True)
    return p.returncode != 0


def _baseline(args):
    if args.since:
        return manifest.at(args.since), None, f"{args.since}"
    rec = manifest.load_green("any")
    if rec:
        return rec["manifest"], rec.get("env"), manifest.describe(rec)
    rev, label = manifest.upstream_base()
    return manifest.at(rev), None, f"{label} (no green run recorded yet)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--since", help="compare against this git revision")
    ap.add_argument("--explain", action="store_true", help="print the selection, run nothing")
    ap.add_argument("--force", action="store_true", help="run even if nothing changed")
    ap.add_argument("--all", action="store_true", help="run every test and check this tier knows")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    python = sys.executable
    tree = manifest.current()
    env = manifest.env_key(python)
    old, old_env, label = _baseline(args)
    changed = manifest.diff(old, tree)
    env_moved = old_env is not None and old_env != env

    if not changed and not env_moved and not (args.force or args.all or args.explain):
        print(f"Nothing changed since {label}. Log of that run: {LOG.relative_to(REPO)}")
        return 0

    graph = build_graph(tree)
    if args.all:
        sel = everything(graph, rules, "asked for --all")
    elif env_moved:
        sel = everything(graph, rules, "installed packages changed since the last green run")
    else:
        sel = select(graph, rules, changed)

    counts = {n: len(t) for n, t in sel.tests.items()}
    head = f"{len(changed)} changed file{'s' if len(changed) != 1 else ''} since {label}"
    print(head)
    for path, reason in sel.escalated:
        print(f"  ! running everything - {path}: {reason}")
    if sel.everything and not sel.escalated:
        print(f"  ! running everything - {sel.everything_reason}")
    for path, note in sel.notes:
        print(f"  · {path}: {note}")
    if sel.unreached:
        print(f"  · no test reaches: {', '.join(sel.unreached)}")

    if args.explain:
        for name, picked in sel.tests.items():
            print(f"\n{name} suite - {len(picked)} test files")
            for t in sorted(picked):
                print("  " + explain(graph, sel, t))
        steps = ", ".join(f"{s.id} {s.name}" for s in rules.STEPS if s.id in sel.steps) or "none"
        print(f"\nsteps: {steps}")
        print(f"parity gates: {', '.join(sorted(sel.gates)) or 'none'}")
        return 0

    if sel.empty():
        print("Nothing to run for these changes.")
        manifest.save_green("fast", tree, env)
        return 0

    # Heavy pieces run ONE AFTER ANOTHER, each with every core; the short checks run beside them.
    # MEASURED 2026-09-10: splitting the cores three ways put the root suite on 4 workers and the
    # everything-run took 219s against ~172s for the same pieces in sequence at full width.
    light = [_step_job(s, python) for s in rules.STEPS if s.id in sel.steps and not s.heavy]
    heavy = []
    for suite in rules.SUITES:
        files = sel.tests.get(suite.name, {})
        if files:
            heavy.append(_pytest_job(suite, files, python, CPU))
    if sel.gates:
        heavy.append(_gates_job(sel.gates, python, CPU))
    # A heavy step goes LAST, so the short checks beside the lane have finished before it starts.
    heavy += [_step_job(s, python) for s in rules.STEPS if s.id in sel.steps and s.heavy]
    jobs = light + heavy

    if any(j.kind == "pytest" and "-n" in j.cmd for j in jobs) and _xdist_missing(python):
        print(f"\n  pytest-xdist is not installed in {python}")
        print(f"  Install it:  {python} -m pip install -r command-center/backend/requirements.txt")
        return 1

    parts = [f"{j.label} ({j.detail})" if j.detail else j.label for j in jobs]
    print("Running: " + ", ".join(parts))
    done = []
    with ThreadPoolExecutor(max_workers=4) as side, ThreadPoolExecutor(max_workers=1) as main_lane:
        futures = [side.submit(j.run) for j in light] + [main_lane.submit(j.run) for j in heavy]
        for fut in as_completed(futures):
            job = fut.result()
            done.append(job)
            tail, extra = _summary(job)
            mark = "✓" if job.ok else "✗"
            print(f"  {mark} {job.label}{' - ' + tail if tail else ''} ({job.secs:.1f}s)")
            for line in extra:
                print(f"      {line.strip()}")

    manifest.LOG_DIR.mkdir(exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write(f"{head}\n")
        for p, s in sorted(changed.items()):
            fh.write(f"  {s:8} {p}\n")
        for job in done:
            fh.write(f"\n{'━' * 72}\n{job.label}  exit {job.code}  {job.secs:.1f}s\n")
            fh.write(" ".join(job.cmd) + "\n\n" + job.out)

    wall = time.monotonic() - t0
    if all(j.ok for j in done):
        manifest.save_green("fast", tree, env)
        print(f"All green in {wall:.1f}s - recorded. Log: {LOG.relative_to(REPO)}")
        return 0
    print(f"Red after {wall:.1f}s. Full output and tracebacks: {LOG.relative_to(REPO)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
