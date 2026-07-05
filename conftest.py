"""Repo-root pytest bootstrap.

The canonical engines live under ``engines/`` but are imported by bare
package name (``from market_structure import ...``, ``from sessions import ...``)
to match the rest of the repo's "put the dir on sys.path, import bare" pattern.
Putting ``engines/`` on sys.path here makes every engine importable from any
test in the suite, including the ones that don't bootstrap their own path.
"""
import sys
from pathlib import Path

_ENGINES = Path(__file__).resolve().parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))
