"""`orchestrator.run_cycle` -- composing OBSERVE(optional) -> IMPACT ->
SELECT AGENTS -> EVALUATE -> APPROVAL GATE over one real project.

Every assertion here treats the underlying Phase 1-5 functions as ground
truth: this module is proven to compose them and close their write path, not
to reimplement any of their logic. The worked example at the end reproduces
Phase 5's `gate.architecture-review` BLOCKED -> PASS result through the
orchestrator instead of manual `GateState(...)` construction.
"""

from __future__ import annotations

import copy

import pytest

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.delivery import ChecklistItemResult
from domain.metamodel.enums import AgentLifecycle, ChecklistItemStatus, EntityType, GateStatus
from domain.metamodel.relationships import relationship
from engines.gates import evaluate_checklist
from engines.impact import DeliveryObligation
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from project_graph.service import ProjectGraphService

from orchestrator import (
    EvaluationRequest,
    GateRequest,
    OrchestratorError,
    run_cycle,
)
from orchestrator.gate import assemble_gate_state, assess_gate_readiness
from orchestrator.staffing import engineering_roles_for_obligation, select_agents

from tests.conftest import make_change, make_project, make_requirement, ref

PROJECT_REF = ref(EntityType.PROJECT, "demo")


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture(autouse=True)
def _register_project(service, registry) -> None:
    service.register_project(make_project("demo"))


REGRESSION_VALUES = {
    "impacted-asset-coverage": 0.95,
    "test-selection-false-positive-rate": 0.03,
    "selection-explainability": 0.85,
    "test-readiness-evidence-conformance": 0.97,
}
ARCHITECTURE_VALUES = {
    "nfr-coverage": 0.95,
    "integration-points-identified": 1.0,
    "vendor-neutral-justification": 0.9,
    "cost-estimate-completeness": 0.75,
}
ARCHITECTURE_ARTIFACT = EntityRef(type=EntityType.DELIVERY_ARTIFACT, id="solution-architecture-v1")


class TestStaffing:
    def test_regression_engineer_chain_resolves_and_writes_a_queryable_implemented_by_edge(
        self, service, registry, delivery_model, graph
    ) -> None:
        obligation = DeliveryObligation(kind="task", key="task.regression-test", reason="x")
        outcomes = select_agents(service, registry, delivery_model, PROJECT_REF, [obligation])

        regression = next(o for o in outcomes if o.engineering_role_key == "regression-engineer")
        assert regression.staffed_agent_key == "regression-agent"
        assert regression.implemented_by_written is True

        # The staffing decision is now conformance-checked, not just
        # role-matched: task.regression-test has a real, auto-derived
        # DeliveryContract, and regression-agent's Agent.delivery
        # declarations genuinely satisfy its mandatory controls.
        assert regression.resolution.best_match.conformance is not None
        assert regression.resolution.best_match.conformance.is_eligible is True
        assert regression.resolution.best_match.conformance.contract_key == "contract.regression-test"

        edge = graph.get_relationship(
            EntityRef(type=EntityType.ENGINEERING_ROLE, id="regression-engineer"),
            "IMPLEMENTED_BY",
            EntityRef(type=EntityType.AGENT, id="regression-agent"),
        )
        assert edge is not None

    def test_data_architect_engineering_role_has_zero_candidates_and_writes_nothing(
        self, service, registry, delivery_model, graph
    ) -> None:
        obligation = DeliveryObligation(kind="task", key="task.logical-data-model", reason="x")
        outcomes = select_agents(service, registry, delivery_model, PROJECT_REF, [obligation])

        data_architect_outcomes = [o for o in outcomes if o.engineering_role_key == "data-architect"]
        assert data_architect_outcomes
        for outcome in data_architect_outcomes:
            assert outcome.staffed_agent_key is None
            assert outcome.implemented_by_written is False
            assert not outcome.resolution.is_staffable

        edge = graph.get_relationship(
            EntityRef(type=EntityType.ENGINEERING_ROLE, id="data-architect"),
            "IMPLEMENTED_BY",
            EntityRef(type=EntityType.AGENT, id="regression-agent"),
        )
        assert edge is None

    def test_architecture_signoff_responsibility_has_no_engineering_role_at_all(
        self, registry, delivery_model
    ) -> None:
        obligation = DeliveryObligation(kind="task", key="task.logical-data-model", reason="x")
        chain = engineering_roles_for_obligation(obligation, delivery_model, registry)
        signoff = [c for c in chain if c[1] == "resp.architecture-signoff"]
        assert signoff == [("data-architect", "resp.architecture-signoff", None)]

    def test_non_role_bearing_obligation_kinds_resolve_to_nothing(self, registry, delivery_model) -> None:
        obligation = DeliveryObligation(kind="checklist", key="architecture-checklist", reason="x")
        assert engineering_roles_for_obligation(obligation, delivery_model, registry) == []

    def test_the_same_role_reached_twice_dedups_to_one_graph_edge(
        self, service, registry, delivery_model, graph
    ) -> None:
        obligations = [
            DeliveryObligation(kind="task", key="task.regression-test", reason="a"),
            DeliveryObligation(kind="task", key="task.regression-test", reason="b"),
        ]
        select_agents(service, registry, delivery_model, PROJECT_REF, obligations)
        edges = graph.relationships(
            source=EntityRef(type=EntityType.ENGINEERING_ROLE, id="regression-engineer"),
            type_="IMPLEMENTED_BY",
        )
        assert len(edges) == 1


class TestEvaluateWritePath:
    def test_a_run_evaluation_is_persisted_and_queryable(self, service, registry, metadata, graph) -> None:
        from orchestrator.evaluate import run_evaluations

        subject = EntityRef(type=EntityType.AGENT, id="regression-agent")
        request = EvaluationRequest(
            suite_key="regression-agent-certification", subject_ref=subject, observed_values=REGRESSION_VALUES
        )
        [outcome] = run_evaluations(service, registry, [request])

        assert metadata.get(EntityType.EVALUATION, outcome.evaluation.id) is not None
        edge = graph.get_relationship(outcome.evaluation.ref(), "EVALUATES", subject)
        assert edge is not None

    def test_advance_agent_result_is_persisted(self, service, registry, metadata) -> None:
        from orchestrator.evaluate import run_evaluations

        agent = copy.deepcopy(registry.agents["regression-agent"])
        subject = EntityRef(type=EntityType.AGENT, id="regression-agent")
        request = EvaluationRequest(
            suite_key="regression-agent-certification",
            subject_ref=subject,
            observed_values=REGRESSION_VALUES,
            advance_agent=agent,
            advance_to=AgentLifecycle.EVALUATED,
        )
        run_evaluations(service, registry, [request])

        assert agent.status is AgentLifecycle.EVALUATED
        stored = metadata.get(EntityType.AGENT, "regression-agent")
        assert stored.payload["status"] == "EVALUATED"

    def test_delivery_artifact_subject_evaluation_writes_cleanly(self, service, registry, metadata) -> None:
        """Proves the EVALUATES registry fix -- without DeliveryArtifact in
        EVALUATES.target_types this raises IngestionError."""
        from orchestrator.evaluate import run_evaluations

        request = EvaluationRequest(
            suite_key="architecture-quality-evaluation",
            subject_ref=ARCHITECTURE_ARTIFACT,
            observed_values=ARCHITECTURE_VALUES,
        )
        [outcome] = run_evaluations(service, registry, [request])
        assert outcome.evaluation.passed is True

    def test_failing_evaluation_is_still_persisted_via_run_cycle(
        self, service, registry, delivery_model, metadata
    ) -> None:
        """A failing advance_agent precondition is recorded as a
        CycleFailure by run_cycle, not a rollback of the already-written
        Evaluation."""
        agent = copy.deepcopy(registry.agents["regression-agent"])  # starts CANDIDATE
        subject = EntityRef(type=EntityType.AGENT, id="regression-agent")
        request = EvaluationRequest(
            suite_key="regression-agent-certification",
            subject_ref=subject,
            observed_values=REGRESSION_VALUES,
            advance_agent=agent,
            advance_to=AgentLifecycle.CERTIFIED,  # illegal jump from CANDIDATE
        )
        report = run_cycle(
            service, registry, delivery_model, PROJECT_REF, metadata, evaluation_requests=[request]
        )
        assert report.failed
        assert report.failed[0].kind == "evaluation_failed"
        # The evaluation itself was written before advance_agent was attempted.
        evaluations = metadata.list(EntityType.EVALUATION)
        assert len(evaluations) == 1


class TestGateStateAssembly:
    def test_passed_evaluations_sourced_from_the_metadata_plane_not_a_literal(
        self, service, registry, metadata
    ) -> None:
        from orchestrator.evaluate import run_evaluations

        subject = EntityRef(type=EntityType.AGENT, id="regression-agent")
        run_evaluations(
            service,
            registry,
            [
                EvaluationRequest(
                    suite_key="regression-agent-certification",
                    subject_ref=subject,
                    observed_values=REGRESSION_VALUES,
                )
            ],
        )
        state = assemble_gate_state(
            service, metadata, PROJECT_REF, GateRequest(gate_key="gate.test-readiness")
        )
        assert state.passed_evaluations == {"regression-agent-certification"}

    def test_traceability_sourced_from_project_requirements_not_a_literal(
        self, service, registry, metadata, graph
    ) -> None:
        requirement = make_requirement("REQ-1")
        service.ingest_entity(requirement)
        task = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
        graph.upsert_relationship(
            relationship("TRACED_TO", ref(EntityType.REQUIREMENT, "REQ-1"), task, discovered_by="fixture")
        )

        state = assemble_gate_state(
            service, metadata, PROJECT_REF, GateRequest(gate_key="gate.test-readiness")
        )
        from engines.impact import traceability_score

        expected = traceability_score([ref(EntityType.REQUIREMENT, "REQ-1")], graph)
        assert state.traceability == expected
        assert state.traceability < 1.0  # the chain is real and genuinely incomplete

    def test_zero_requirements_reads_as_fully_traceable(self, service, metadata) -> None:
        state = assemble_gate_state(
            service, metadata, PROJECT_REF, GateRequest(gate_key="gate.test-readiness")
        )
        assert state.traceability == 1.0

    def test_unknown_gate_key_raises(self, service, metadata, delivery_model) -> None:
        from orchestrator.errors import UnknownGateError

        with pytest.raises(UnknownGateError):
            assess_gate_readiness(
                service, metadata, delivery_model, PROJECT_REF, GateRequest(gate_key="gate.no-such-gate")
            )


class TestArchitectureReviewWorkedExampleThroughTheOrchestrator:
    GATE = "gate.architecture-review"
    CHECKLIST = "architecture-checklist"

    def _gate_request(self, delivery_model) -> GateRequest:
        items = delivery_model.items_for(self.CHECKLIST)
        results = [
            ChecklistItemResult(item_key=item.item_key, status=ChecklistItemStatus.PASS) for item in items
        ]
        outcome = evaluate_checklist(delivery_model.checklists[self.CHECKLIST], items, results)
        return GateRequest(
            gate_key=self.GATE,
            present_artifact_kinds={"solution-architecture", "logical-data-model"},
            checklist_outcomes={self.CHECKLIST: outcome},
            satisfied_evidence={"ev.architecture"},
            approvals={"solution-architect"},
        )

    def test_gate_is_blocked_with_no_evaluation(self, service, metadata, delivery_model) -> None:
        readiness = assess_gate_readiness(
            service, metadata, delivery_model, PROJECT_REF, self._gate_request(delivery_model)
        )
        assert readiness.status is GateStatus.BLOCKED
        assert any(item.requirement == "architecture-quality-evaluation" for item in readiness.blocking_items)

    def test_gate_reaches_pass_once_run_cycle_runs_the_evaluation(
        self, service, registry, metadata, delivery_model
    ) -> None:
        report = run_cycle(
            service,
            registry,
            delivery_model,
            PROJECT_REF,
            metadata,
            evaluation_requests=[
                EvaluationRequest(
                    suite_key="architecture-quality-evaluation",
                    subject_ref=ARCHITECTURE_ARTIFACT,
                    observed_values=ARCHITECTURE_VALUES,
                )
            ],
            gates=[self._gate_request(delivery_model)],
        )
        assert report.gate_readiness[self.GATE].status is GateStatus.PASS
        assert report.failed == []


class TestFullCycle:
    def test_change_impact_staffing_evaluation_and_gate_compose(
        self, service, registry, metadata, graph, delivery_model
    ) -> None:
        stg = ref(EntityType.PIPELINE, "stg_customers")
        task = ref(EntityType.DELIVERY_TASK, "task.regression-test")
        code = ref(EntityType.CODE_ARTIFACT, "customer_address.sql")
        graph.upsert_relationship(relationship("DEPENDS_ON", stg, code, discovered_by="dbt"))
        graph.upsert_relationship(relationship("GOVERNS", task, stg, discovered_by="delivery"))

        change = make_change(impacted_refs=[code])
        subject = EntityRef(type=EntityType.AGENT, id="regression-agent")

        report = run_cycle(
            service,
            registry,
            delivery_model,
            PROJECT_REF,
            metadata,
            change=change,
            evaluation_requests=[
                EvaluationRequest(
                    suite_key="regression-agent-certification",
                    subject_ref=subject,
                    observed_values=REGRESSION_VALUES,
                )
            ],
            gates=[GateRequest(gate_key="gate.test-readiness")],
        )

        assert report.impact is not None
        assert [o.key for o in report.impact.delivery.triggered_tasks] == ["task.regression-test"]
        assert any(
            o.engineering_role_key == "regression-engineer" and o.staffed_agent_key == "regression-agent"
            for o in report.staffing
        )
        assert len(report.evaluations) == 1
        assert "gate.test-readiness" in report.gate_readiness
        assert report.failed == []


class TestObserveStep:
    def test_observe_reproduces_the_worked_example_discovery_numbers(
        self, service, registry, metadata, delivery_model
    ) -> None:
        from pathlib import Path

        from discovery.extraction.replay_client import ReplayExtractionClient
        from domain.metamodel.entities.technical import Project as ProjectEntity
        from domain.metamodel.enums import ProvenanceState
        from orchestrator import ObserveRequest

        repo_root = Path(__file__).resolve().parents[2].parent / "agentic-ai-ollama-demo"
        golden_dir = Path(__file__).resolve().parents[1] / "fixtures" / "discovery" / "golden"
        if not repo_root.is_dir():
            pytest.skip("agentic-ai-ollama-demo/ sibling project not present")

        # A fresh project distinct from PROJECT_REF's "demo" -- discovery
        # registers its own project inside discover_project.
        observe_project = ProjectEntity(
            id="ollama-demo",
            name="ollama-demo",
            entity_type=EntityType.PROJECT,
            provenance=ProvenanceState.OBSERVED,
            confidence=1.0,
            discovered_by="test",
        )
        observe_project_ref = observe_project.ref()
        client = ReplayExtractionClient(golden_dir)

        report = run_cycle(
            service,
            registry,
            delivery_model,
            observe_project_ref,
            metadata,
            observe=ObserveRequest(
                project=observe_project, client=client, repository_root=repo_root, repository_id="ollama-demo"
            ),
        )
        assert report.discovery is not None
        assert report.discovery.entities_ingested == 21
        assert report.discovery.relationships_ingested == 34


class TestObserveProjectMismatch:
    def test_mismatched_observe_project_raises(self, service, registry, metadata, delivery_model) -> None:
        from pathlib import Path

        from orchestrator import ObserveRequest

        class _FakeClient:
            def extract(self, *, prompt, response_schema):
                raise AssertionError("should never be called")

        other_project = make_project("someone-else")
        with pytest.raises(OrchestratorError):
            run_cycle(
                service,
                registry,
                delivery_model,
                PROJECT_REF,
                metadata,
                observe=ObserveRequest(
                    project=other_project, client=_FakeClient(), repository_root=Path(".")
                ),
            )
