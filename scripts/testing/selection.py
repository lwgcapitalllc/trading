"""From a set of changed files to the exact tests, steps and parity gates they can reach.

Generic over its inputs: the graph (`graph.py`) and the repo's rules (`rules.py`) are handed in, so
the tests can drive it with a throwaway repo and a throwaway rule set.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Selection:
    tests: dict = field(default_factory=dict)  # suite name -> {test path: node it was reached from}
    steps: set = field(default_factory=set)  # run_all_tests.sh step ids
    gates: set = field(default_factory=set)  # component dirs whose parity gate runs
    escalated: list = field(default_factory=list)  # (path, reason) - these run EVERYTHING
    notes: list = field(default_factory=list)  # (path, what it means) - nothing to run for it
    unreached: list = field(default_factory=list)  # changed code that no test, step or gate reaches
    came_from: dict = field(default_factory=dict)
    everything: bool = False
    everything_reason: str = ""

    def empty(self) -> bool:
        return not (any(self.tests.values()) or self.steps or self.gates)


def everything(graph, rules, reason: str) -> Selection:
    sel = Selection(everything=True, everything_reason=reason)
    for suite in rules.SUITES:
        sel.tests[suite.name] = {t: "everything" for t in graph.py if suite.owns(t)}
    sel.steps = {s.id for s in rules.STEPS}
    sel.gates = {c for c, _g in rules.gates()}
    return sel


def select(graph, rules, changed: dict) -> Selection:
    """`changed` maps a repo-relative path to "added", "modified" or "deleted"."""
    sel = Selection()
    seeds, forced_tests, forced_suites = set(), set(), set()

    for path, status in sorted(changed.items()):
        matched = False
        acts = [a for glob, a in rules.TABLE if rules.matches(path, (glob,))]
        for a in acts:
            matched = True
            if a.note:
                sel.notes.append((path, a.note))
            forced_tests.update(a.tests)
            forced_suites.update(a.suites)
            if a.escalate:
                sel.escalated.append((path, a.escalate))
            if a.gate:
                sel.gates.add(rules.component_of_golden(path))
        for step in rules.STEPS:
            if step.globs and rules.matches(path, step.globs):
                sel.steps.add(step.id)
                matched = True
        if path.endswith(".py"):
            matched = True
            if status == "deleted":
                seeds |= graph.importers_of_deleted(path)
            else:
                seeds.add(path)
        else:
            if all(a.readers for a in acts):
                found = graph.readers(path, by_name=all(a.by_name for a in acts))
                if found:
                    seeds |= found
                    matched = True
            if all(a.package for a in acts):
                pkg = graph.package_of(path)
                if pkg:
                    seeds.add(pkg)
                    matched = True
        if not matched:
            if rules.matches(path, rules.INERT):
                continue
            if path.startswith(rules.CODE_TREES):
                sel.escalated.append((path, "nothing I can see reads it, and it is in a code tree"))
            else:
                sel.notes.append((path, "nothing I can see reads it"))

    if sel.escalated:
        full = everything(graph, rules, "; ".join(f"{p}: {r}" for p, r in sel.escalated))
        full.escalated, full.notes = sel.escalated, sel.notes
        return full

    sel.came_from = graph.reach(seeds)
    for suite in rules.SUITES:
        picked = graph.tests_reached(sel.came_from, suite)
        for t in forced_tests:
            if suite.owns(t) and t in graph.files:
                picked.setdefault(t, "named by a file table rule")
        if suite.name in forced_suites:
            for t in graph.py:
                if suite.owns(t):
                    picked.setdefault(t, f"{suite.name} suite configuration changed")
        sel.tests[suite.name] = picked
    for step in rules.STEPS:
        if step.script and step.script in sel.came_from:
            sel.steps.add(step.id)
    gate_scripts = rules.gates()
    runner_moved = rules.GATE_RUNNER in sel.came_from
    for component, gate in gate_scripts:
        if runner_moved or gate in sel.came_from:
            sel.gates.add(component)

    # Changed code nothing reaches is not a failure - it is worth SAYING, because "all green" over
    # a file no test imports reads as tested.
    targets = {s.script for s in rules.STEPS if s.script} | {g for _c, g in gate_scripts}
    targets.add(rules.GATE_RUNNER)
    for path, status in sorted(changed.items()):
        if not path.endswith(".py") or status == "deleted":
            continue
        reach = graph.reach({path})
        hit = any(graph.tests_reached(reach, s) for s in rules.SUITES) or (targets & set(reach))
        if not hit:
            sel.unreached.append(path)
    return sel


def explain(graph, sel: Selection, test: str) -> str:
    """One line: how a selected test was reached, from the changed file that picked it."""
    for picked in sel.tests.values():
        if test not in picked:
            continue
        via = picked[test]
        if isinstance(via, str) and via not in sel.came_from:
            return f"{test}  <- {via}"
        node = via
        chain = graph.chain(sel.came_from, node)
        parts = [n if isinstance(n, str) else f"{n[0]} (fixture {n[1]})" for n in chain]
        if via != test:
            parts.append(test)
        return "  <-  ".join(reversed(parts))
    return f"{test}  (not selected)"
