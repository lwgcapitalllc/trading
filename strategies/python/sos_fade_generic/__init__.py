"""sos_fade_generic — SOS Fade stripped to its core, for running on other instruments.

Spec: docs/SOS_FADE_GENERIC_SPEC.md
Rules: `CLAUDE.md` in this package.

    SosFadeGenericConfig    — the few settings it exposes; `to_sos_fade()` pins the rest off
    SosFadeGenericStrategy  — SosFadeStrategy, built from that config
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .config import TARGETS, SosFadeGenericConfig
from .strategy import SosFadeGenericStrategy

__all__ = ["LAB_STRATEGY", "TARGETS", "SosFadeGenericConfig", "SosFadeGenericStrategy"]

# ── Lab registration (runner="python") — same contract as `sos_fade/__init__.py` ─────────
# `config` is the GENERIC dataclass, so the lab's form shows only its few settings.
LAB_STRATEGY = {
    "name": "SOS Fade Generic",
    "config": SosFadeGenericConfig,
    "strategy": SosFadeGenericStrategy,
    "suggested_instrument": "XAUUSD",
    # M15 because that is the frame SOS Fade's gate and every figure it rests on are M15. A
    # DEFAULT the lab fills in, never a refusal.
    "suggested_bar_value": 15,
    "category": "reversal",
    "self_sizing": True,
    "chart_tag": "SOS GEN",
}
