"""Loaded at start-up by every Python process a test run starts (this folder is on PYTHONPATH).

Two hooks, each armed by an environment variable and inert without it:

- LWG_MUTATION=<file>     -> scripts/testing/mutate.py's planted bug is served for one file
- LWG_TEST_NO_LIVE_VPS=1  -> scripts/testing/vps_guard.py refuses the live trading box

⚠ **They share ONE file because Python imports only the FIRST `sitecustomize` on the path** - two
separate ones would silently shadow each other, and a planted bug that never reaches a subprocess
reads exactly like a bug nothing checks.

⚠ **The mutation hook is installed FIRST.** The guard is itself loaded from source here, so with
the order reversed a bug planted in the guard never reached a child process and every guard test
that runs one read the planted bug as SURVIVED (found by the guard's own mutation map, 2026-09-10).

⚠ Standard library only, and it imports nothing of the repo's by name: it runs before the process
has a path to import from, and a failure here would break every process the test run starts.
"""

import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

_mutation = os.environ.get("LWG_MUTATION")
if _mutation:
    with open(_mutation, encoding="utf-8") as _fh:
        _m = json.load(_fh)
    import importlib.machinery as _mach

    _orig_get_code = _mach.SourceFileLoader.get_code

    def _get_code(self, fullname, _orig=_orig_get_code, _m=_m):
        path = os.path.realpath(self.get_filename(fullname))
        if path == _m["target"]:
            return compile(_m["source"], path, "exec", dont_inherit=True)
        return _orig(self, fullname)

    _mach.SourceFileLoader.get_code = _get_code

if os.environ.get("LWG_TEST_NO_LIVE_VPS") == "1":
    _spec = importlib.util.spec_from_file_location(
        "_lwg_vps_guard", os.path.join(os.path.dirname(_HERE), "vps_guard.py")
    )
    _guard = importlib.util.module_from_spec(_spec)
    # REGISTERED under a fixed name, in every process that loads it: a refusal raised in a worker
    # travels back to the test by PICKLE, which looks its class up by module name - unregistered,
    # the test saw "can't pickle LiveVpsCall" instead of the sentence saying what was refused.
    sys.modules.setdefault("_lwg_vps_guard", _guard)
    _spec.loader.exec_module(_guard)
    _guard.install()
