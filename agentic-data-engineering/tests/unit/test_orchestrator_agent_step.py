"""`orchestrator.agent_step.run_agents()` / `run_cycle(agent_run_requests=...)`
composition -- an `AgentRunOutcome` linked to a real `StaffingOutcome`, and a
`CycleFailure` recorded (not raised) when a run fails under
`on_error="collect"`."""

from __future__ import annotations

import pytest

from domain.metamodel.enums import ApprovalLevel, AutomationLevel, EntityType
from engines.impact import DeliveryObligation
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from project_graph.service import ProjectGraphService

from agent_runtime.approval import AutomationLevelApprovalPolicy
from agent_runtime.llm import AgentTurnResult
from agent_runtime.simulated_tools import SimulatedToolExecutor

from orchestrator import run_cycle
from orchestrator.agent_step import AgentRunRequest, run_agents
from orchestrator.staffing import select_agents

from tests.conftest import make_policy, make_project, ref

PROJECT_REF = ref(EntityType.PROJECT, "demo")


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture(autouse=True)
def _register_project(service) -> None:
    service.register_project(make_project("demo"))


class _FakeClient:
    def next_turn(self, *, system_prompt, messages, tools) -> AgentTurnResult:
        return AgentTurnResult(text="ok", tool_calls=[], stop_reason="end_turn")


def _request(agent_key: str, staffing_outcome=None) -> AgentRunRequest:
    return AgentRunRequest(
        agent_key=agent_key,
        task="do the work",
        llm_client=_FakeClient(),
        tool_executor=SimulatedToolExecutor(),
        context_policy=make_policy(max_tokens=100_000),
        approval_policy=AutomationLevelApprovalPolicy(
            automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS, granted=ApprovalLevel.SAMPLED_QA
        ),
        staffing_outcome=staffing_outcome,
    )


class TestRunAgentsLinksBackToStaffing:
    def test_agent_run_outcome_carries_its_staffing_outcome(self, service, registry, delivery_model) -> None:
        obligation = DeliveryObligation(kind="task", key="task.regression-test", reason="x")
        staffing = select_agents(service, registry, delivery_model, PROJECT_REF, [obligation])
        regression_outcome = next(o for o in staffing if o.engineering_role_key == "regression-engineer")

        outcomes = run_agents(registry, [_request(regression_outcome.staffed_agent_key, regression_outcome)])
        assert len(outcomes) == 1
        assert outcomes[0].staffing_outcome is regression_outcome
        assert outcomes[0].report.completed is True


class TestRunCycleComposesAgentRuns:
    def test_agent_runs_appear_on_the_cycle_report(self, service, registry, delivery_model, metadata) -> None:
        report = run_cycle(
            service,
            registry,
            delivery_model,
            PROJECT_REF,
            metadata,
            agent_run_requests=[_request("regression-agent")],
        )
        assert len(report.agent_runs) == 1
        assert report.agent_runs[0].agent_key == "regression-agent"
        assert report.failed == []

    def test_unknown_agent_key_is_a_collected_failure_not_a_crash(
        self, service, registry, delivery_model, metadata
    ) -> None:
        report = run_cycle(
            service,
            registry,
            delivery_model,
            PROJECT_REF,
            metadata,
            agent_run_requests=[_request("does-not-exist")],
        )
        assert report.agent_runs == []
        assert len(report.failed) == 1
        assert report.failed[0].kind == "agent_run_failed"

    def test_fail_fast_reraises_instead_of_collecting(self, service, registry, delivery_model, metadata) -> None:
        with pytest.raises(Exception):
            run_cycle(
                service,
                registry,
                delivery_model,
                PROJECT_REF,
                metadata,
                agent_run_requests=[_request("does-not-exist")],
                on_error="fail_fast",
            )
