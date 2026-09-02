"""Elo model research pipeline state, model configuration, and seeding definitions."""

from cfb_model.elo.seed import seed_history
from cfb_model.elo.state import EloModel, EloState

# Production Graduated Constants (SPEC-phase2 §6.4 & §11)
ELO_PER_POINT = 16.0
K = 30.0
MOV_DENOMINATOR_FLOOR = 0.05

__all__ = [
    "EloModel",
    "EloState",
    "seed_history",
    "ELO_PER_POINT",
    "K",
    "MOV_DENOMINATOR_FLOOR",
]
