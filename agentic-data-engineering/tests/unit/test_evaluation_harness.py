"""`engines/evaluation/`: scoring a suite, reducing history into the set
`GateState` needs, and gating `Agent` lifecycle transitions.

The worked end-to-end example proves the seam between this new engine and
the untouched `engines.gates` -- `gate.architecture-review`'s evaluations
dimension goes from BLOCKED to a real passing score once a real `Evaluation`
is run and fed through `passed_evaluation_keys()`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.delivery import ChecklistItemResult
from domain.metamodel.entities.evaluation import Evaluation, EvaluationMetric, EvaluationSuite
from domain.metamodel.enums import AgentLifecycle, ChecklistItemStatus, EntityType, GateDimension, GateStatus
from engines.evaluation import advance_agent, passed_evaluation_keys, run_suite
from engines.gates import GateState, assess_gate, evaluate_checklist

from tests.conftest import make_agent, make_evaluation, ref

REGRESSION_SUITE = "regression-agent-certification"
SUBJECT = EntityRef(type=EntityType.AGENT, id="regression-agent")

PASSING_VALUES = {
    "impacted-asset-coverage": 0.95,
    "test-selection-false-positive-rate": 0.03,
    "selection-explainability": 0.85,
    "test-readiness-evidence-conformance": 0.97,
}


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


class TestEvaluationSuiteLevel:
    def test_tool_is_now_a_known_level(self) -> None:
        """Found gap (Phase 10): CandidateTool had no honest `level` to
        evaluate under -- `skill | agent | workflow | ecosystem` had no
        `tool`. See metamodel-registry/evaluation_suites.yaml's
        foundry-candidate-tool-completeness."""
        suite = EvaluationSuite(
            id="s", name="s", entity_type=EntityType.EVALUATION_SUITE, suite_key="s", level="tool"
        )
        assert suite.level == "tool"

    def test_an_unknown_level_still_raises(self) -> None:
        with pytest.raises(ValidationError, match="level must be one of"):
            EvaluationSuite(
                id="s", name="s", entity_type=EntityType.EVALUATION_SUITE, suite_key="s", level="bogus"
            )


class TestRunSuite:
    def test_passing_observed_values_produce_a_passing_evaluation(self, registry) -> None:
        suite = registry.evaluation_suites[REGRESSION_SUITE]
        evaluation = run_suite(suite, registry.evaluation_metrics, SUBJECT, PASSING_VALUES)
        assert evaluation.passed is True
        assert evaluation.score == pytest.approx(1.0)
        assert evaluation.delivery_score == pytest.approx(1.0)
        assert evaluation.subject_ref == SUBJECT
        assert evaluation.suite_ref.id == REGRESSION_SUITE

    def test_a_blocking_metric_below_threshold_fails_the_run(self, registry) -> None:
        suite = registry.evaluation_suites[REGRESSION_SUITE]
        failing = {**PASSING_VALUES, "impacted-asset-coverage": 0.70}
        evaluation = run_suite(suite, registry.evaluation_metrics, SUBJECT, failing)
        assert evaluation.passed is False
        blocking_result = next(
            r for r in evaluation.metric_results if r.metric_key == "impacted-asset-coverage"
        )
        assert blocking_result.blocking is True
        assert blocking_result.passed is False

    def test_never_produces_a_passing_evaluation_with_a_blocking_failure(self, registry) -> None:
        """Consistency with Evaluation's own _blocking_failure_fails_the_run
        validator -- run_suite must never hand it a contradiction. Uses the
        real metric_results run_suite computed, not invented ones, and
        proves that claiming passed=True over them is exactly what the
        entity's own validator rejects."""
        suite = registry.evaluation_suites[REGRESSION_SUITE]
        failing = {**PASSING_VALUES, "impacted-asset-coverage": 0.70}
        evaluation = run_suite(suite, registry.evaluation_metrics, SUBJECT, failing)
        assert evaluation.passed is False
        with pytest.raises(ValidationError, match="blocking metrics failed"):
            Evaluation(
                id=evaluation.id,
                name=evaluation.name,
                entity_type=EntityType.EVALUATION,
                suite_ref=evaluation.suite_ref,
                subject_ref=evaluation.subject_ref,
                score=evaluation.score,
                delivery_score=evaluation.delivery_score,
                passed=True,
                metric_results=evaluation.metric_results,
            )

    def test_suite_with_no_delivery_dimension_metric_scores_delivery_as_trivially_complete(
        self,
    ) -> None:
        metric = EvaluationMetric(
            id="m1",
            name="m1",
            entity_type=EntityType.EVALUATION_METRIC,
            metric_key="m1",
            dimension="technical",
            threshold=0.5,
        )
        suite = EvaluationSuite(
            id="s1",
            name="s1",
            entity_type=EntityType.EVALUATION_SUITE,
            suite_key="s1",
            level="skill",
            metric_refs=[ref(EntityType.EVALUATION_METRIC, "m1")],
        )
        evaluation = run_suite(suite, {"m1": metric}, SUBJECT, {"m1": 0.9})
        assert evaluation.delivery_score == 1.0

    def test_unknown_metric_key_raises(self, registry) -> None:
        suite = registry.evaluation_suites[REGRESSION_SUITE]
        with pytest.raises(ValueError, match="unknown metric"):
            run_suite(
                suite.model_copy(
                    update={"metric_refs": [ref(EntityType.EVALUATION_METRIC, "no-such-metric")]}
                ),
                registry.evaluation_metrics,
                SUBJECT,
                {},
            )

    def test_missing_observed_value_raises(self, registry) -> None:
        suite = registry.evaluation_suites[REGRESSION_SUITE]
        with pytest.raises(ValueError, match="no observed value"):
            run_suite(suite, registry.evaluation_metrics, SUBJECT, {})


class TestPassedEvaluationKeys:
    def test_later_evaluation_wins_over_an_earlier_opposite_outcome(self) -> None:
        older_pass = make_evaluation("e1", suite_key="s", subject_ref=SUBJECT, passed=True)
        older_pass = older_pass.model_copy(update={"evaluated_at": _at(2026, 1, 1)})
        newer_fail = make_evaluation("e2", suite_key="s", subject_ref=SUBJECT, passed=False)
        newer_fail = newer_fail.model_copy(update={"evaluated_at": _at(2026, 2, 1)})
        assert passed_evaluation_keys([older_pass, newer_fail]) == set()

        older_fail = older_pass.model_copy(update={"passed": False, "evaluated_at": _at(2026, 1, 1)})
        newer_pass = newer_fail.model_copy(update={"passed": True, "evaluated_at": _at(2026, 2, 1)})
        assert passed_evaluation_keys([older_fail, newer_pass]) == {"s"}

    def test_subject_ref_filters_other_subjects(self) -> None:
        other_subject = EntityRef(type=EntityType.AGENT, id="someone-else")
        mine = make_evaluation("e1", suite_key="s", subject_ref=SUBJECT, passed=True)
        theirs = make_evaluation("e2", suite_key="s2", subject_ref=other_subject, passed=True)
        assert passed_evaluation_keys([mine, theirs], subject_ref=SUBJECT) == {"s"}

    def test_empty_input_is_empty_output(self) -> None:
        assert passed_evaluation_keys([]) == set()


class TestAdvanceAgent:
    def test_gated_target_with_no_evaluation_raises(self) -> None:
        agent = make_agent("a", "regression-engineer")
        with pytest.raises(ValueError, match="without a passing Evaluation"):
            advance_agent(agent, AgentLifecycle.EVALUATED)

    def test_gated_target_with_a_failing_evaluation_raises(self) -> None:
        agent = make_agent("a", "regression-engineer")
        subject = ref(EntityType.AGENT, "a")
        evaluation = make_evaluation("e1", subject_ref=subject, passed=False)
        with pytest.raises(ValueError, match="did not pass"):
            advance_agent(agent, AgentLifecycle.EVALUATED, evaluation=evaluation)

    def test_gated_target_with_a_wrong_subject_evaluation_raises(self) -> None:
        agent = make_agent("a", "regression-engineer")
        wrong_subject = ref(EntityType.AGENT, "someone-else")
        evaluation = make_evaluation("e1", subject_ref=wrong_subject, passed=True)
        with pytest.raises(ValueError, match="does not evaluate agent"):
            advance_agent(agent, AgentLifecycle.EVALUATED, evaluation=evaluation)

    def test_valid_passing_evaluation_advances_the_agent(self) -> None:
        agent = make_agent("a", "regression-engineer")  # starts DRAFT
        agent.transition_to(AgentLifecycle.CANDIDATE)
        subject = ref(EntityType.AGENT, "a")
        evaluation = make_evaluation("e1", subject_ref=subject, passed=True)
        advancement = advance_agent(agent, AgentLifecycle.EVALUATED, evaluation=evaluation)
        assert agent.status is AgentLifecycle.EVALUATED
        assert advancement.from_status is AgentLifecycle.CANDIDATE
        assert advancement.to_status is AgentLifecycle.EVALUATED
        assert advancement.evaluation_ref is not None

    def test_ungated_target_needs_no_evaluation(self) -> None:
        agent = make_agent("a", "regression-engineer")  # starts DRAFT
        advancement = advance_agent(agent, AgentLifecycle.CANDIDATE)
        assert agent.status is AgentLifecycle.CANDIDATE
        assert advancement.evaluation_ref is None

    def test_illegal_structural_transition_still_raises_even_with_a_valid_evaluation(self) -> None:
        agent = make_agent("a", "regression-engineer")  # starts DRAFT
        agent.transition_to(AgentLifecycle.CANDIDATE)
        subject = ref(EntityType.AGENT, "a")
        evaluation = make_evaluation("e1", subject_ref=subject, passed=True)
        with pytest.raises(ValueError, match="illegal agent lifecycle transition"):
            advance_agent(agent, AgentLifecycle.CERTIFIED, evaluation=evaluation)


class TestArchitectureReviewWorkedExample:
    GATE = "gate.architecture-review"
    CHECKLIST = "architecture-checklist"
    SUITE = "architecture-quality-evaluation"
    ARTIFACT = EntityRef(type=EntityType.DELIVERY_ARTIFACT, id="solution-architecture-v1")

    PASSING_VALUES = {
        "nfr-coverage": 0.95,
        "integration-points-identified": 1.0,
        "vendor-neutral-justification": 0.9,
        "cost-estimate-completeness": 0.75,
    }

    def _pass_all_checklist_items(self, delivery_model, checklist_key):
        items = delivery_model.items_for(checklist_key)
        results = [
            ChecklistItemResult(item_key=item.item_key, status=ChecklistItemStatus.PASS)
            for item in items
        ]
        return items, results

    def _complete_state(self, delivery_model, *, passed_evaluations: set[str]) -> GateState:
        items, results = self._pass_all_checklist_items(delivery_model, self.CHECKLIST)
        outcome = evaluate_checklist(delivery_model.checklists[self.CHECKLIST], items, results)
        return GateState(
            present_artifact_kinds={"solution-architecture", "logical-data-model"},
            checklist_outcomes={self.CHECKLIST: outcome},
            satisfied_evidence={"ev.architecture"},
            approvals={"solution-architect"},
            traceability=1.0,
            passed_evaluations=passed_evaluations,
        )

    def test_gate_is_blocked_with_no_evaluation(self, delivery_model) -> None:
        state = self._complete_state(delivery_model, passed_evaluations=set())
        readiness = assess_gate(delivery_model.gates[self.GATE], state)
        assert readiness.status is GateStatus.BLOCKED
        assert any(item.requirement == self.SUITE for item in readiness.blocking_items)

    def test_gate_reaches_pass_once_a_real_evaluation_is_run(self, registry, delivery_model) -> None:
        suite = registry.evaluation_suites[self.SUITE]
        evaluation = run_suite(suite, registry.evaluation_metrics, self.ARTIFACT, self.PASSING_VALUES)
        assert evaluation.passed is True

        passed_keys = passed_evaluation_keys([evaluation])
        assert passed_keys == {self.SUITE}

        state = self._complete_state(delivery_model, passed_evaluations=passed_keys)
        readiness = assess_gate(delivery_model.gates[self.GATE], state)

        assert readiness.dimension(GateDimension.EVALUATIONS).score == pytest.approx(1.0)
        assert readiness.status is GateStatus.PASS
        assert not readiness.blocking_items
