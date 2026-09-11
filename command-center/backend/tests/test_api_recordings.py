"""Every backend answer a browser spec replays still has the shape its route declares.

The Bots page's browser checks run OFFLINE (`frontend/tests/offline.ts`): the page's reads are
answered from recordings under `frontend/tests/recordings/`, taken once from a real backend by
`frontend/scripts/record-api.mjs`. That keeps every check off the live trading box — and makes the
recording a claim about this backend's SHAPE that goes stale in silence: rename a field here and
the browser suite goes on replaying the old name, green, over a page that no longer reads it.

So each recorded answer is validated against the `response_model` of the GET route that would
serve it, matched in FastAPI's own order. A red here means re-record, not relax.

⚠ A required field ADDED to a model fails this; an optional one does not, because an old answer
without it is still an answer the page can receive.

Mutation map, RUN 2026-09-10 (3 planted, 3 killed):
  a required field added to BotSnapshot (mutate.py)         -> matches_its_routes_response_model
  validation skipped (planted in a throwaway worktree)      -> the_check_can_fail
  any GET route matches any path (throwaway worktree)       -> matches_... (7 of 7 red)
⚠ The last two had to be planted in a worktree copy: mutate.py cannot plant in a TEST file (pytest
reads those from disk) and reported both as SURVIVED until it was taught to refuse.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from main import app
from pydantic import TypeAdapter, ValidationError

RECORDINGS = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "recordings"


def _route_for(path: str):
    """The GET route FastAPI would serve `path` with — first match in registration order."""
    for route in app.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods and route.path_regex.match(path):
            return route
    return None


def _validate(path: str, answer) -> None:
    route = _route_for(path.split("?", 1)[0])
    assert route is not None, (
        f"{path}: no GET route serves it - the recording names a dead endpoint"
    )
    assert route.response_model is not None, f"{path}: its route declares no response model"
    TypeAdapter(route.response_model).validate_python(answer)


_CASES = [
    (rec.stem, path, answer)
    for rec in sorted(RECORDINGS.glob("*.json"))
    for path, answer in json.loads(rec.read_text(encoding="utf-8"))["answers"].items()
]


def test_there_are_recordings_to_check():
    """Finding none is a FAILURE: a moved folder would otherwise check nothing, green."""
    assert _CASES, f"no recorded answers under {RECORDINGS}"


@pytest.mark.parametrize("name,path,answer", _CASES, ids=[f"{n}:{p}" for n, p, _ in _CASES])
def test_a_recorded_answer_matches_its_routes_response_model(name, path, answer):
    _validate(path, answer)


def test_the_check_can_fail():
    """The snapshot without its bots is refused — so the model under test has teeth, and the
    route lookup found the snapshot's route rather than one that accepts anything."""
    snapshot = next(a for n, p, a in _CASES if p == "/bots/snapshot")
    broken = copy.deepcopy(snapshot)
    del broken["bots"]
    with pytest.raises(ValidationError):
        _validate("/bots/snapshot", broken)
