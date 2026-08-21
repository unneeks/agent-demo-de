"""Gating a marketplace candidate's ``CandidateReview.candidate_status``
transitions on a passing, subject-matching ``Evaluation``.

A structural mirror of ``engines/evaluation/lifecycle.py::advance_agent()``
-- same precondition-then-``transition_to()`` shape, same "gated targets
need a passing, subject-matching evaluation" rule -- but checking against
a candidate's own id rather than a registered ``Agent.agent_key``.
``advance_agent()`` itself cannot be reused: it hardcodes
``evaluation.subject_ref.type is EntityType.AGENT``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel, utc_now
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.entities.foundry import CandidateAgent, CandidateSkill, CandidateTool
from domain.metamodel.enums import CandidateStatus, EntityType

Candidate = CandidateSkill | CandidateTool | CandidateAgent

#: Transitions that require a passing, subject-matching Evaluation.
#: CANDIDATE->REJECTED needs none (a human can reject without ever running
#: an evaluation); EVALUATED->CANDIDATE needs none either (retreating, not
#: proving fitness).
GATED_TRANSITIONS: frozenset[CandidateStatus] = frozenset(
    {CandidateStatus.EVALUATED, CandidateStatus.CERTIFIED}
)

_CANDIDATE_ENTITY_TYPES: frozenset[EntityType] = frozenset(
    {EntityType.CANDIDATE_SKILL, EntityType.CANDIDATE_TOOL, EntityType.CANDIDATE_AGENT}
)


class CandidateAdvancement(MetamodelModel):
    """Audit record of one gated (or ungated) candidate lifecycle move."""

    candidate_id: str
    from_status: CandidateStatus
    to_status: CandidateStatus
    evaluation_ref: EntityRef | None = None
    advanced_at: datetime = Field(default_factory=utc_now)


def advance_candidate(
    candidate: Candidate,
    target: CandidateStatus,
    *,
    evaluation: Evaluation | None = None,
    now: datetime | None = None,
) -> CandidateAdvancement:
    """Move ``candidate.review`` to ``target``, requiring a passing
    evaluation for gated targets. Mutates ``candidate.review`` in place
    (matching ``CandidateReview.transition_to()``'s own mutate-and-return-
    None style) and returns an audit record.
    """
    if target in GATED_TRANSITIONS:
        if evaluation is None:
            raise ValueError(
                f"candidate {candidate.id!r} cannot advance to {target.value} without a "
                "passing Evaluation"
            )
        if evaluation.subject_ref.type not in _CANDIDATE_ENTITY_TYPES or (
            evaluation.subject_ref.id != candidate.id
        ):
            raise ValueError(
                f"evaluation {evaluation.id!r} does not evaluate candidate {candidate.id!r} "
                f"(subject_ref={evaluation.subject_ref})"
            )
        if not evaluation.passed:
            raise ValueError(
                f"evaluation {evaluation.id!r} for candidate {candidate.id!r} did not pass; "
                f"cannot advance to {target.value}"
            )

    from_status = candidate.review.candidate_status
    # evaluation_ref must be set BEFORE the status assignment: CandidateReview
    # has validate_assignment=True, so assigning candidate_status re-runs
    # _gated_status_needs_evaluation immediately -- it must already see a
    # populated evaluation_ref for a gated target, not one set afterwards.
    if evaluation is not None:
        candidate.review.evaluation_ref = evaluation.ref(pinned=True)
    candidate.review.transition_to(target)

    return CandidateAdvancement(
        candidate_id=candidate.id,
        from_status=from_status,
        to_status=target,
        evaluation_ref=evaluation.ref(pinned=True) if evaluation is not None else None,
        advanced_at=now or utc_now(),
    )
