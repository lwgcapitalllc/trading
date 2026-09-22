"""A strategy's `.meta.json` in the wrong SHAPE must not take down the whole scan (2026-09-22).

`smc_session_sweep.meta.json` stated its `params` as an object keyed by setting name, where every
other strategy states a LIST of `{"name": ...}`. Iterating the object yields the key strings, and
`_apply_param_meta` called `.get` on a string: an AttributeError, so Scan Strategies answered 500
for every strategy, not just the one with the odd file. The docstring already promised that a
malformed meta file is a no-op; this pins that it is.

RED before: both tests raised AttributeError. MUTATION: drop the list/dict checks in
`_apply_param_meta` -> both go red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import strategy_scanner  # noqa: E402

_PARAMS = [{"name": "risk", "type": "float", "default": 1.0}]


def _meta(tmp_path, body) -> Path:
    p = tmp_path / "x.meta.json"
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


def test_params_stated_as_an_object_is_a_no_op_not_a_crash(tmp_path):
    meta = _meta(tmp_path, {"params": {"risk": {"label": "Risk"}}})
    assert strategy_scanner._apply_param_meta([dict(p) for p in _PARAMS], meta) == _PARAMS


def test_a_non_object_entry_is_skipped_and_the_rest_still_apply(tmp_path):
    meta = _meta(tmp_path, {"params": ["risk", {"name": "risk", "label": "Risk"}]})
    out = strategy_scanner._apply_param_meta([dict(p) for p in _PARAMS], meta)
    assert out[0]["label"] == "Risk"
