"""``engines/foundry/evaluation.py`` + ``engines/foundry/lifecycle.py``:
structural completeness scoring and candidate lifecycle gating.

Mirrors ``test_evaluation_harness.py``'s own ``advance_agent()`` tests
structurally.
"""

from __future__ import annotations

import pytest

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.foundry import CandidateReview
from domain.metamodel.enums import CandidateStatus, EntityType
from engines.evaluation.harness import run_suite
from engines.foundry.evaluation import score_candidate_completeness
from engines.foundry.lifecycle import advance_candidate

from tests.conftest import (
    make_candidate_agent,
    make_candidate_skill,
    make_candidate_tool,
    make_evaluation,
    make_pattern,
    make_skill,
)


class TestScoreCandidateCompleteness:
    def test_skill_with_io_and_checklist_items_scores_fully_complete(self) -> None:
        skill = make_skill(
            "skill.x",
            inputs={"a": "b"},
            outputs={"c": "d"},
            discharges_checklist_items=["ITEM-01"],
        )
        candidate = make_candidate_skill("cs1", proposed_key="skill.x", proposed_skill=skill)
        pattern = make_pattern("p1", frequency=5, observation_refs=[
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o1"),
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o2"),
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o3"),
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o4"),
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o5"),
        ])
        scores = score_candidate_completeness(candidate, pattern)
        assert scores["candidate-io-contract-completeness"] == 1.0
        assert scores["candidate-checklist-traceability"] == 1.0
        assert scores["candidate-pattern-support"] == 1.0

    def test_skill_with_no_io_scores_incomplete(self) -> None:
        candidate = make_candidate_skill("cs1")
        pattern = make_pattern("p1")
        scores = score_candidate_completeness(candidate, pattern)
        assert scores["candidate-io-contract-completeness"] == 0.0
        assert scores["candidate-checklist-traceability"] == 0.0

    def test_tool_completeness_looks_at_actions_not_io_fields(self) -> None:
        from domain.metamodel.entities.organization import Tool, ToolAction
        from domain.metamodel.enums import ActionClass

        tool = Tool(
            id="tool.x", name="tool.x", entity_type=EntityType.TOOL, tool_key="tool.x",
            actions=[ToolAction(name="run", action_class=ActionClass.READ_ONLY, input_schema={"a": "b"}, output_schema={"c": "d"})],
        )
        candidate = make_candidate_tool("ct1", proposed_key="tool.x", proposed_tool=tool)
        pattern = make_pattern("p1", frequency=2, observation_refs=[
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o1"),
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id="o2"),
        ])
        scores = score_candidate_completeness(candidate, pattern)
        assert scores["candidate-io-contract-completeness"] == 1.0
        assert scores["candidate-pattern-support"] == pytest.approx(0.4)

    def test_pattern_support_caps_at_one(self) -> None:
        candidate = make_candidate_agent("ca1")
        pattern = make_pattern("p1", frequency=10, observation_refs=[
            EntityRef(type=EntityType.ENGINEERING_OBSERVATION, id=f"o{i}") for i in range(10)
        ])
        scores = score_candidate_completeness(candidate, pattern)
        assert scores["candidate-pattern-support"] == 1.0


class TestRunSuiteIntegration:
    def test_foundry_candidate_skill_completeness_suite_scores_a_real_candidate(self, registry) -> None:
        candidate = make_candidate_skill("cs1")
        pattern = make_pattern("p1")
        suite = registry.evaluation_suites["foundry-candidate-skill-completeness"]
        observed = score_candidate_completeness(candidate, pattern)
        evaluation = run_suite(suite, registry.evaluation_metrics, candidate.ref(), observed)
        assert evaluation.subject_ref == candidate.ref()
        # No inputs/outputs by default -- the blocking io-contract metric fails.
        assert evaluation.passed is False

    def test_foundry_candidate_tool_completeness_suite_exists_and_scores(self, registry) -> None:
        assert "foundry-candidate-tool-completeness" in registry.evaluation_suites
        candidate = make_candidate_tool("ct1")
        pattern = make_pattern("p1")
        suite = registry.evaluation_suites["foundry-candidate-tool-completeness"]
        observed = score_candidate_completeness(candidate, pattern)
        evaluation = run_suite(suite, registry.evaluation_metrics, candidate.ref(), observed)
        assert evaluation.subject_ref == candidate.ref()

    def test_foundry_candidate_agent_completeness_suite_exists(self, registry) -> None:
        assert "foundry-candidate-agent-completeness" in registry.evaluation_suites


class TestAdvanceCandidate:
    def test_ungated_retreat_needs_no_evaluation(self) -> None:
        """EVALUATED -> CANDIDATE is not in GATED_TRANSITIONS -- retreating
        never needs a fresh Evaluation, only proving fitness forward does.
        """
        already_evaluated = make_candidate_skill(
            "cs1",
            review=CandidateReview(
                candidate_status=CandidateStatus.EVALUATED,
                proposed_key="cs1",
                derived_from_pattern_refs=[EntityRef(type=EntityType.ENGINEERING_PATTERN, id="p1")],
                rationale="test",
                evaluation_ref=EntityRef(type=EntityType.EVALUATION, id="e1"),
            ),
        )
        advancement = advance_candidate(already_evaluated, CandidateStatus.CANDIDATE)
        assert already_evaluated.review.candidate_status is CandidateStatus.CANDIDATE
        assert advancement.to_status is CandidateStatus.CANDIDATE

    def test_gated_transition_without_evaluation_raises(self) -> None:
        candidate = make_candidate_skill("cs1")
        with pytest.raises(ValueError, match="cannot advance"):
            advance_candidate(candidate, CandidateStatus.EVALUATED)

    def test_gated_transition_with_wrong_subject_evaluation_raises(self) -> None:
        candidate = make_candidate_skill("cs1")
        other_ref = EntityRef(type=EntityType.CANDIDATE_SKILL, id="not-this-one")
        evaluation = make_evaluation(subject_ref=other_ref)
        with pytest.raises(ValueError, match="does not evaluate candidate"):
            advance_candidate(candidate, CandidateStatus.EVALUATED, evaluation=evaluation)

    def test_gated_transition_with_failing_evaluation_raises(self) -> None:
        candidate = make_candidate_skill("cs1")
        evaluation = make_evaluation(subject_ref=candidate.ref(), passed=False, score=0.1)
        with pytest.raises(ValueError, match="did not pass"):
            advance_candidate(candidate, CandidateStatus.EVALUATED, evaluation=evaluation)

    def test_gated_transition_with_passing_evaluation_advances(self) -> None:
        candidate = make_candidate_skill("cs1")
        evaluation = make_evaluation(subject_ref=candidate.ref(), passed=True)
        advancement = advance_candidate(candidate, CandidateStatus.EVALUATED, evaluation=evaluation)
        assert candidate.review.candidate_status is CandidateStatus.EVALUATED
        assert candidate.review.evaluation_ref is not None
        assert advancement.to_status is CandidateStatus.EVALUATED

    def test_illegal_jump_is_rejected(self) -> None:
        candidate = make_candidate_skill("cs1")
        evaluation = make_evaluation(subject_ref=candidate.ref(), passed=True)
        with pytest.raises(ValueError, match="illegal candidate transition"):
            advance_candidate(candidate, CandidateStatus.CERTIFIED, evaluation=evaluation)
