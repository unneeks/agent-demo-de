"""``domain/metamodel/entities/foundry/``: EngineeringObservation,
EngineeringPattern, CandidateReview, CandidateSkill/Tool/Agent.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.metamodel.entities.foundry import CandidateReview
from domain.metamodel.enums import CANDIDATE_STATUS_TRANSITIONS, CandidateStatus, EntityType, ProvenanceState

from tests.conftest import make_candidate_agent, make_candidate_skill, make_candidate_tool, make_observation, make_pattern, ref


class TestEngineeringObservation:
    def test_inherits_provenance_invariants(self) -> None:
        with pytest.raises(ValidationError):
            make_observation("o1", provenance=ProvenanceState.INFERRED, confidence=None)

    def test_observed_default_is_constructible(self) -> None:
        observation = make_observation("o1")
        assert observation.provenance is ProvenanceState.OBSERVED
        assert observation.confidence == 1.0


class TestEngineeringPattern:
    def test_requires_at_least_two_observations(self) -> None:
        with pytest.raises(ValidationError, match="at least 2"):
            make_pattern("p1", observation_refs=[ref(EntityType.ENGINEERING_OBSERVATION, "o1")])

    def test_frequency_must_match_observation_refs_length(self) -> None:
        with pytest.raises(ValidationError, match="frequency must equal"):
            make_pattern(
                "p1",
                observation_refs=[
                    ref(EntityType.ENGINEERING_OBSERVATION, "o1"),
                    ref(EntityType.ENGINEERING_OBSERVATION, "o2"),
                ],
                frequency=5,
            )

    def test_valid_pattern_constructs(self) -> None:
        pattern = make_pattern("p1")
        assert pattern.frequency == 2
        assert pattern.synthesized is False


class TestCandidateReview:
    def test_rejected_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="REJECTED requires rejection_reason"):
            CandidateReview(
                candidate_status=CandidateStatus.REJECTED,
                proposed_key="skill.x",
                derived_from_pattern_refs=[ref(EntityType.ENGINEERING_PATTERN, "p1")],
                rationale="r",
            )

    def test_evaluated_requires_evaluation_ref(self) -> None:
        with pytest.raises(ValidationError, match="EVALUATED requires evaluation_ref"):
            CandidateReview(
                candidate_status=CandidateStatus.EVALUATED,
                proposed_key="skill.x",
                derived_from_pattern_refs=[ref(EntityType.ENGINEERING_PATTERN, "p1")],
                rationale="r",
            )

    def test_certified_requires_evaluation_ref(self) -> None:
        with pytest.raises(ValidationError, match="CERTIFIED requires evaluation_ref"):
            CandidateReview(
                candidate_status=CandidateStatus.CERTIFIED,
                proposed_key="skill.x",
                derived_from_pattern_refs=[ref(EntityType.ENGINEERING_PATTERN, "p1")],
                rationale="r",
            )

    def test_gated_status_with_evaluation_ref_constructs(self) -> None:
        review = CandidateReview(
            candidate_status=CandidateStatus.EVALUATED,
            proposed_key="skill.x",
            derived_from_pattern_refs=[ref(EntityType.ENGINEERING_PATTERN, "p1")],
            rationale="r",
            evaluation_ref=ref(EntityType.EVALUATION, "e1"),
        )
        assert review.candidate_status is CandidateStatus.EVALUATED

    @pytest.mark.parametrize(
        ("start", "target", "legal"),
        [
            (CandidateStatus.CANDIDATE, CandidateStatus.EVALUATED, True),
            (CandidateStatus.CANDIDATE, CandidateStatus.REJECTED, True),
            (CandidateStatus.CANDIDATE, CandidateStatus.CERTIFIED, False),
            (CandidateStatus.EVALUATED, CandidateStatus.CERTIFIED, True),
            (CandidateStatus.EVALUATED, CandidateStatus.CANDIDATE, True),
            (CandidateStatus.CERTIFIED, CandidateStatus.CANDIDATE, False),
            (CandidateStatus.REJECTED, CandidateStatus.CANDIDATE, False),
        ],
    )
    def test_transition_legality_matches_the_transition_table(
        self, start: CandidateStatus, target: CandidateStatus, legal: bool
    ) -> None:
        assert (target in CANDIDATE_STATUS_TRANSITIONS[start]) is legal

    def test_illegal_transition_raises(self) -> None:
        review = CandidateReview(
            proposed_key="skill.x",
            derived_from_pattern_refs=[ref(EntityType.ENGINEERING_PATTERN, "p1")],
            rationale="r",
        )
        with pytest.raises(ValueError, match="illegal candidate transition"):
            review.transition_to(CandidateStatus.CERTIFIED)


class TestCandidateKeyConsistency:
    def test_candidate_skill_key_mismatch_is_rejected(self) -> None:
        mismatched_skill = make_candidate_skill("other", proposed_key="skill.b").proposed_skill
        with pytest.raises(ValidationError, match="must match proposed_skill.skill_key"):
            make_candidate_skill("cs1", proposed_key="skill.a", proposed_skill=mismatched_skill)

    def test_candidate_tool_key_mismatch_is_rejected(self) -> None:
        mismatched_tool = make_candidate_tool("other", proposed_key="tool.b").proposed_tool
        with pytest.raises(ValidationError, match="must match proposed_tool.tool_key"):
            make_candidate_tool("ct1", proposed_key="tool.a", proposed_tool=mismatched_tool)

    def test_candidate_agent_key_mismatch_is_rejected(self) -> None:
        mismatched_agent = make_candidate_agent("other", proposed_key="agent.b").proposed_agent
        with pytest.raises(ValidationError, match="must match proposed_agent.agent_key"):
            make_candidate_agent("ca1", proposed_key="agent.a", proposed_agent=mismatched_agent)

    def test_candidate_tool_key_matches_by_default(self) -> None:
        good = make_candidate_tool("ct1")
        assert good.review.proposed_key == good.proposed_tool.tool_key

    def test_candidate_agent_key_matches_by_default(self) -> None:
        good = make_candidate_agent("ca1")
        assert good.review.proposed_key == good.proposed_agent.agent_key
