"""mpc_realign — MPC REALIGN: internal-structure realignment after an external false break.

Spec: docs/MPC_REALIGN_SPEC.md
"""
from .config import RealignConfig  # noqa: F401
from .strategy import MpcRealignStrategy  # noqa: F401

LAB_STRATEGY = MpcRealignStrategy
