"""EloState and EloModel schemas for the research pipeline (SPEC-phase2 §4.1)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(strict=True, extra="forbid", frozen=True)


class EloModel(BaseModel):
    """Fitted constants recorded inside each state snapshot."""

    model_config = _STRICT

    elo_per_point: float
    k: float
    mov_damping: float
    mov_denominator_floor: float
    regression_to_mean: float
    hfa_source: str = "fitted"  # "fitted" for history, "sagarin" for live


class EloState(BaseModel):
    """The stored Elo state document for historical and fitted runs."""

    model_config = _STRICT

    schema_version: int = Field(ge=2)  # Bumped to 2 for SPEC-phase2 §4.1
    season: int = Field(ge=1869)
    week: str = Field(min_length=1)
    generated_at: datetime
    seeded_from: str = Field(min_length=1)
    games_applied: int = Field(ge=0)
    folded_from: datetime | None = None
    through_kickoff: datetime | None = None
    model: EloModel  # Embedded model block storing the fitted constants
    ratings: dict[str, float]
