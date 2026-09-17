"""Entity-level invariants: lifecycle, action classification, and structural gates.

Each is a rule that makes governance mechanical rather than remembered, and each
has a test asserting that the violation is refused.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.metamodel.entities.delivery import Approval, DeliveryArtifact
from domain.metamodel.entities.evaluation import Evaluation, MetricResult
from domain.metamodel.entities.organization import ToolAction
from domain.metamodel.entities.shared.capability import CapabilityGap
from domain.metamodel.entities.shared.work import Decision
from domain.metamodel.entities.technical import DataProfile, Deployment
from domain.metamodel.enums import (
    AGENT_LIFECYCLE_TRANSITIONS,
    ActionClass,
    AgentLifecycle,
    ApprovalLevel,
    DeploymentStage,
    EntityType,
    ExecutionModel,
    GateDecision,
    ProvenanceState,
)
from tests.conftest import make_agent, make_tool, ref


class TestAgentLifecycle:
    def test_certification_cannot_be_skipped(self) -> None:
        agent = make_agent("a", "regression-engineer")
        with pytest.raises(ValueError, match="illegal agent lifecycle transition"):
            agent.transition_to(AgentLifecycle.DEPLOYED)

    def test_full_promotion_path(self) -> None:
        agent = make_agent("a", "regression-engineer")
        for stage in (
            AgentLifecycle.CANDIDATE,
            AgentLifecycle.EVALUATED,
            AgentLifecycle.CERTIFIED,
            AgentLifecycle.DEPLOYED,
            AgentLifecycle.MONITORED,
        ):
            agent.transition_to(stage)
        assert agent.is_deployable

    def test_retirement_is_terminal(self) -> None:
        agent = make_agent("a", "regression-engineer")
        agent.transition_to(AgentLifecycle.RETIRED)
        with pytest.raises(ValueError):
            agent.transition_to(AgentLifecycle.DRAFT)

    def test_every_state_has_a_rule(self) -> None:
        assert set(AGENT_LIFECYCLE_TRANSITIONS) == set(AgentLifecycle)


class TestAgentExternalProvider:
    """ADR-0014: EXTERNAL_AGENT needs to name which external system executes."""

    def test_external_agent_without_a_provider_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="EXTERNAL_AGENT but no external_provider"):
            make_agent(
                "a", "regression-engineer", execution_model=ExecutionModel.EXTERNAL_AGENT
            )

    def test_external_agent_with_a_provider_constructs(self) -> None:
        agent = make_agent(
            "a",
            "regression-engineer",
            execution_model=ExecutionModel.EXTERNAL_AGENT,
            external_provider="github-copilot-coding-agent",
        )
        assert agent.external_provider == "github-copilot-coding-agent"

    def test_non_external_agent_leaves_provider_unset(self) -> None:
        agent = make_agent("a", "regression-engineer")
        assert agent.external_provider is None


class TestActionClassification:
    def test_action_class_is_mandatory(self) -> None:
        with pytest.raises(ValidationError):
            ToolAction(name="mystery")  # type: ignore[call-arg]

    @pytest.mark.parametrize(
        "action_class", [ActionClass.HIGH_RISK_WRITE, ActionClass.DESTRUCTIVE]
    )
    def test_dangerous_actions_cannot_waive_approval(self, action_class) -> None:
        with pytest.raises(ValidationError, match="always need a human"):
            ToolAction(
                name="danger", action_class=action_class, minimum_approval=ApprovalLevel.NONE
            )

    def test_max_action_class_surfaces_worst_case(self) -> None:
        tool = make_tool(
            "github",
            actions=[
                ToolAction(name="read", action_class=ActionClass.READ_ONLY),
                ToolAction(
                    name="merge",
                    action_class=ActionClass.HIGH_RISK_WRITE,
                    minimum_approval=ApprovalLevel.SINGLE_REVIEWER,
                ),
            ],
        )
        assert tool.max_action_class is ActionClass.HIGH_RISK_WRITE


class TestDeploymentGates:
    def _subject(self, version: str | None = "1.0.0"):
        return ref(EntityType.AGENT, "regression-agent", version)

    def test_production_requires_certification_and_approval(self) -> None:
        with pytest.raises(ValidationError, match="without certification"):
            Deployment(
                id="d1",
                name="prod",
                entity_type=EntityType.DEPLOYMENT,
                subject_ref=self._subject(),
                stage=DeploymentStage.PRODUCTION,
            )

    def test_production_requires_a_gate_approval(self) -> None:
        with pytest.raises(ValidationError, match="gate approval"):
            Deployment(
                id="d2",
                name="prod",
                entity_type=EntityType.DEPLOYMENT,
                subject_ref=self._subject(),
                stage=DeploymentStage.PRODUCTION,
                evaluation_ref=ref(EntityType.EVALUATION, "e1"),
            )

    def test_deployment_must_pin_a_version(self) -> None:
        with pytest.raises(ValidationError, match="pin an exact version"):
            Deployment(
                id="d3",
                name="shadow",
                entity_type=EntityType.DEPLOYMENT,
                subject_ref=self._subject(version=None),
                stage=DeploymentStage.SHADOW,
            )

    def test_shadow_needs_no_evaluation(self) -> None:
        """Shadow exists precisely to gather the evidence production requires."""
        deployment = Deployment(
            id="d4",
            name="shadow",
            entity_type=EntityType.DEPLOYMENT,
            subject_ref=self._subject(),
            stage=DeploymentStage.SHADOW,
        )
        assert deployment.stage is DeploymentStage.SHADOW


class TestApprovalRecords:
    def test_conditional_approval_must_state_conditions(self) -> None:
        with fail_on(ValidationError, "at least one stated condition"):
            Approval(
                id="a1",
                name="approval",
                entity_type=EntityType.APPROVAL,
                gate_ref=ref(EntityType.APPROVAL_GATE, "g"),
                subject_ref=ref(EntityType.CHANGE, "c"),
                decision=GateDecision.APPROVE_WITH_CONDITIONS,
                approver="alex",
            )

    def test_rejection_must_state_a_rationale(self) -> None:
        with fail_on(ValidationError, "must record a rationale"):
            Approval(
                id="a2",
                name="approval",
                entity_type=EntityType.APPROVAL,
                gate_ref=ref(EntityType.APPROVAL_GATE, "g"),
                subject_ref=ref(EntityType.CHANGE, "c"),
                decision=GateDecision.REJECT,
                approver="alex",
            )

    def test_approval_records_the_readiness_it_saw(self) -> None:
        """So a later reviewer can tell whether the decision was well informed."""
        approval = Approval(
            id="a3",
            name="approval",
            entity_type=EntityType.APPROVAL,
            gate_ref=ref(EntityType.APPROVAL_GATE, "g"),
            subject_ref=ref(EntityType.CHANGE, "c"),
            decision=GateDecision.APPROVE,
            approver="alex",
            readiness_snapshot={"CHECKLISTS": 1.0, "TRACEABILITY": 0.87},
        )
        assert approval.readiness_snapshot["TRACEABILITY"] == 0.87


class TestDecisionAudit:
    def test_claimed_approval_must_name_the_approver(self) -> None:
        with fail_on(ValidationError, "names no approver"):
            Decision(
                id="dec1",
                name="merge",
                entity_type=EntityType.DECISION,
                summary="Approve the merge.",
                outcome="approve",
                approval_level=ApprovalLevel.SINGLE_REVIEWER,
            )


class TestEvaluationGates:
    def test_blocking_failure_overrides_a_good_score(self) -> None:
        with fail_on(ValidationError, "blocking metrics failed"):
            Evaluation(
                id="e1",
                name="eval",
                entity_type=EntityType.EVALUATION,
                suite_ref=ref(EntityType.EVALUATION_SUITE, "s"),
                subject_ref=ref(EntityType.AGENT, "a"),
                score=0.95,
                delivery_score=0.95,
                passed=True,
                metric_results=[
                    MetricResult(
                        metric_key="security", value=0.4, threshold=0.9, passed=False, blocking=True
                    )
                ],
            )

    def test_trust_score_is_limited_by_the_weaker_dimension(self) -> None:
        """A 98% technical score must not paper over a 40% conformance score."""
        evaluation = Evaluation(
            id="e2",
            name="eval",
            entity_type=EntityType.EVALUATION,
            suite_ref=ref(EntityType.EVALUATION_SUITE, "s"),
            subject_ref=ref(EntityType.AGENT, "a"),
            score=0.98,
            delivery_score=0.40,
            passed=True,
        )
        assert evaluation.trust_score == pytest.approx(0.40)

    def test_weighted_score_can_be_taken_per_dimension(self) -> None:
        results = [
            MetricResult(metric_key="a", dimension="technical", value=1, threshold=1, passed=True),
            MetricResult(
                metric_key="b", dimension="delivery", value=0, threshold=1, passed=False
            ),
        ]
        assert Evaluation.weighted_score(results, "technical") == 1.0
        assert Evaluation.weighted_score(results, "delivery") == 0.0
        assert Evaluation.weighted_score([]) == 0.0


class TestCapabilityGap:
    def test_gap_can_reference_either_capability_kind(self) -> None:
        gap = CapabilityGap(
            id="g1",
            name="gap",
            entity_type=EntityType.CAPABILITY_GAP,
            provenance=ProvenanceState.INFERRED,
            confidence=0.8,
            project_ref=ref(EntityType.PROJECT, "demo"),
            capability_ref=ref(EntityType.DELIVERY_CAPABILITY, "change-assurance"),
            capability_key="change-assurance",
            current_maturity=1,
            desired_maturity=4,
        )
        assert gap.is_delivery_gap and gap.gap_size == 3

    def test_gap_must_point_at_a_capability(self) -> None:
        with fail_on(ValidationError, "must point at a Capability"):
            CapabilityGap(
                id="g2",
                name="gap",
                entity_type=EntityType.CAPABILITY_GAP,
                provenance=ProvenanceState.INFERRED,
                confidence=0.8,
                project_ref=ref(EntityType.PROJECT, "demo"),
                capability_ref=ref(EntityType.PIPELINE, "stg"),
                capability_key="x",
                current_maturity=1,
                desired_maturity=2,
            )

    def test_negative_gap_is_rejected(self) -> None:
        with fail_on(ValidationError, "not a gap"):
            CapabilityGap(
                id="g3",
                name="gap",
                entity_type=EntityType.CAPABILITY_GAP,
                provenance=ProvenanceState.INFERRED,
                confidence=0.7,
                project_ref=ref(EntityType.PROJECT, "demo"),
                capability_ref=ref(EntityType.CAPABILITY, "streaming"),
                capability_key="streaming",
                current_maturity=4,
                desired_maturity=2,
            )


class TestDeliveryArtifacts:
    def test_approved_artifact_names_its_approver(self) -> None:
        with fail_on(ValidationError, "names no approver"):
            DeliveryArtifact(
                id="a",
                name="a",
                entity_type=EntityType.DELIVERY_ARTIFACT,
                provenance=ProvenanceState.OBSERVED,
                discovered_by="fixture",
                artifact_key="a",
                artifact_kind="logical-data-model",
                status="approved",
            )


class TestDataProfile:
    """Held separate from DataAsset for the same reason SchemaDefinition is:
    quality drift needs two structured records to compare, not two opaque
    sentences of Evidence text."""

    def test_constructs_with_free_form_metrics(self) -> None:
        profile = DataProfile(
            id="p1",
            name="raw.customers profile 2026-08-09",
            entity_type=EntityType.DATA_PROFILE,
            provenance=ProvenanceState.OBSERVED,
            discovered_by="great_expectations@0.1",
            asset_ref=ref(EntityType.DATA_ASSET, "raw.customers"),
            metrics={"row_count": 48213.0, "null_rate": 0.002, "customer_id.distinct_count": 48213.0},
            sample_size=48213,
        )
        assert profile.twin.value == "TECHNICAL"
        assert profile.metrics["null_rate"] == 0.002

    def test_inherits_provenance_invariants(self) -> None:
        """A profile is discovered, not declared, like everything else in the twin."""
        with fail_on(ValidationError, "must carry a confidence"):
            DataProfile(
                id="p2",
                name="p2",
                entity_type=EntityType.DATA_PROFILE,
                provenance=ProvenanceState.INFERRED,
                asset_ref=ref(EntityType.DATA_ASSET, "raw.customers"),
            )


class TestSchemaStrictness:
    def test_unknown_fields_are_rejected(self) -> None:
        """A silently dropped field is a discovered fact thrown away."""
        with fail_on(ValidationError, ""):
            make_agent("a", "regression-engineer", unexpected="surprise")

    def test_invalid_semver_is_rejected(self) -> None:
        with fail_on(ValidationError, ""):
            make_agent("a", "regression-engineer", version="v1")


def fail_on(exc_type, match: str):
    """pytest.raises with an optional match, so empty patterns read cleanly."""
    return pytest.raises(exc_type, match=match) if match else pytest.raises(exc_type)
