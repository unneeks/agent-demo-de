"""EngineeringPattern -- a recurring shape found across two or more
``EngineeringObservation``s.

Grouping observations into a pattern is an inference (``provenance=INFERRED``),
unlike the raw observation's own transcription. ``confidence`` is set equal
to ``similarity_score`` at construction by the caller -- one source of
truth, not two independently-drifting numbers.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, ProvenancedEntity, new_ulid
from domain.metamodel.enums import EntityType, Twin


class EngineeringPattern(ProvenancedEntity):
    """A recurring engineering shape, grounded in >=2 observations.

    Single-project scope only (``project_ref`` is singular, not a list) --
    no cross-project/enterprise clustering this phase. ``status`` is
    deliberately reduced to a single ``synthesized`` flag rather than a
    full lifecycle enum: governance of a *reviewable proposal* belongs on
    the candidate (``CandidateStatus``), not on the pattern that fed it.
    """

    entity_type: EntityType = EntityType.ENGINEERING_PATTERN
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    project_ref: EntityRef
    pattern_key: str = Field(min_length=1)
    category: str = Field(
        description="pipeline_shape | test_coverage_shape | delivery_staffing_shape"
    )
    observation_refs: list[EntityRef] = Field(min_length=2)
    frequency: int = Field(ge=2)
    common_activity: str
    common_technology: str | None = None
    common_inputs: list[str] = Field(default_factory=list)
    common_outputs: list[str] = Field(default_factory=list)
    #: Fields present in some but not all grouped observations, noted rather
    #: than silently dropped by the intersection that produces common_inputs/
    #: common_outputs.
    known_variations: list[str] = Field(default_factory=list)
    similarity_score: float = Field(ge=0.0, le=1.0)
    #: Flips true once at least one candidate cites this pattern via SYNTHESIZES.
    synthesized: bool = False

    @model_validator(mode="after")
    def _pattern_must_recur(self) -> EngineeringPattern:
        if len(self.observation_refs) < 2:
            raise ValueError(
                "a pattern must be grounded in at least 2 recurring observations; "
                "a single observation is not yet a pattern."
            )
        if self.frequency != len(self.observation_refs):
            raise ValueError("frequency must equal len(observation_refs); no denormalized drift.")
        return self
