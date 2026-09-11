"""The fast test tier: run only what a change can reach, and remember what already passed.

`scripts/test.sh` is the everyday command; `scripts/run_all_tests.sh` stays the full run. Rules and
when each is required: root `CLAUDE.md` -> *Formatting, linting and the test gate*.

    graph.py     generic: a static import graph and the selection walked over it
    rules.py     concrete: this repo's search roots, suites, steps and file tables
    manifest.py  what the tree held when a run went green, and what moved since
    fast.py      the runner behind scripts/test.sh
    stamp.py     the full run's side of the same records (skip, record, blind spots)
"""
