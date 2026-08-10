"""CandidateReview, CandidateSkill, CandidateTool, CandidateAgent --
unpublished marketplace proposals synthesized from an EngineeringPattern.

Three separate entities, not one polymorphic ``MarketplaceCandidate``:
``Skill``/``Tool``/``Agent`` are already three separate, differently-shaped
entities in this codebase, and a discriminated union would buy nothing the
``SYNTHESIZES`` relationship type's own ``target_types`` restriction
doesn't already express more precisely. The embedded payload is the real
``Skill``/``Tool``/``Agent`` class, not a parallel DTO -- so a future
publish-to-YAML renderer never needs a redesign; there is only one field
list, the same one ``registry.py``'s ``_load_skills``/``_load_tools``/
``_load_agents`` already populate from YAML.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, MetamodelModel, ProvenancedEntity, new_ulid
from domain.metamodel.entities.organization import Agent, Skill, Tool
from domain.metamodel.enums import CANDIDATE_STATUS_TRANSITIONS, CandidateStatus, EntityType, Twin


class CandidateReview(MetamodelModel):
    """Review-workflow state shared by all three candidate kinds.

    Kept as a shared value object rather than duplicated three times, and
    kept strictly separate from ``ProvenanceState``: provenance says how
    much to trust the *fact* that this candidate was synthesized this way
    (INFERRED, from a pattern); ``candidate_status`` says how far the
    *proposal itself* has progressed through human review.
    """

    candidate_status: CandidateStatus = CandidateStatus.CANDIDATE
    proposed_key: str = Field(min_length=1)
    #: A candidate must trace to at least one pattern -- the same citation
    #: discipline Finding._findings_must_be_cited already enforces elsewhere.
    derived_from_pattern_refs: list[EntityRef] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evaluation_ref: EntityRef | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _rejected_needs_reason(self) -> CandidateReview:
        if self.candidate_status is CandidateStatus.REJECTED and not self.rejection_reason:
            raise ValueError(
                "REJECTED requires rejection_reason -- an unattributed rejection is not a decision."
            )
        return self

    @model_validator(mode="after")
    def _gated_status_needs_evaluation(self) -> CandidateReview:
        if (
            self.candidate_status in (CandidateStatus.EVALUATED, CandidateStatus.CERTIFIED)
            and self.evaluation_ref is None
        ):
            raise ValueError(f"{self.candidate_status.value} requires evaluation_ref.")
        return self

    def can_transition_to(self, target: CandidateStatus) -> bool:
        return target in CANDIDATE_STATUS_TRANSITIONS[self.candidate_status]

    def transition_to(self, target: CandidateStatus) -> None:
        if not self.can_transition_to(target):
            raise ValueError(
                f"illegal candidate transition {self.candidate_status.value} -> {target.value}"
            )
        self.candidate_status = target


class CandidateSkill(ProvenancedEntity):
    """An unpublished, synthesized Skill proposal."""

    entity_type: EntityType = EntityType.CANDIDATE_SKILL
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    review: CandidateReview
    proposed_skill: Skill

    @model_validator(mode="after")
    def _key_matches_payload(self) -> CandidateSkill:
        if self.review.proposed_key != self.proposed_skill.skill_key:
            raise ValueError("review.proposed_key must match proposed_skill.skill_key")
        return self


class CandidateTool(ProvenancedEntity):
    """An unpublished, synthesized Tool proposal."""

    entity_type: EntityType = EntityType.CANDIDATE_TOOL
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    review: CandidateReview
    proposed_tool: Tool

    @model_validator(mode="after")
    def _key_matches_payload(self) -> CandidateTool:
        if self.review.proposed_key != self.proposed_tool.tool_key:
            raise ValueError("review.proposed_key must match proposed_tool.tool_key")
        return self


class CandidateAgent(ProvenancedEntity):
    """An unpublished, synthesized Agent proposal."""

    entity_type: EntityType = EntityType.CANDIDATE_AGENT
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    review: CandidateReview
    proposed_agent: Agent

    @model_validator(mode="after")
    def _key_matches_payload(self) -> CandidateAgent:
        if self.review.proposed_key != self.proposed_agent.agent_key:
            raise ValueError("review.proposed_key must match proposed_agent.agent_key")
        return self
