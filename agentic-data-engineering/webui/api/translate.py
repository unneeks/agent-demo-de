"""JSON-safe-knobs -> live-object translation. The one idea this whole
package must not compromise: every write endpoint translates a request
body into the same live Python objects `orchestrator`/`agent_runtime`
already require, server-side only -- never a client-supplied
`ToolExecutor`/`AgentLLMClient`/`ApprovalPolicy`, and never a
client-supplied filesystem path. Shared here so `evaluations.py`,
`gates.py`, `agent_runs.py` and `cycles.py` all call the same builders
instead of duplicating this logic four times.
"""

from __future__ import annotations

from pathlib import Path

from agent_runtime.agentcore_client import AgentCoreHarnessClient
from agent_runtime.anthropic_client import AnthropicAgentClient
from agent_runtime.approval import AutomationLevelApprovalPolicy
from agent_runtime.copilot_cli_client import CopilotCliAgentClient
from agent_runtime.llm import AgentLLMClient
from agent_runtime.local_tool_executor import LocalToolExecutor
from agent_runtime.replay_client import ReplayAgentClient
from agent_runtime.simulated_tools import SimulatedToolExecutor
from agent_runtime.tools import ToolExecutor
from domain.metamodel.registry import MetamodelRegistry

from orchestrator.agent_step import AgentRunRequest
from orchestrator.evaluate import EvaluationRequest
from orchestrator.gate import GateRequest
from orchestrator.workflow import LiveAgentBackend, WorkflowTemplate

from webui.api.errors import MissingWorkflowBackendError, ReplayBackendUnavailableError, UnknownAgentError
from webui.api.schemas import (
    AgentRunHttpRequest,
    EvaluationRunRequest,
    GateAssessRequest,
    WorkflowLiveBackendConfig,
    WorkflowRunRequest,
)


def build_evaluation_request(body: EvaluationRunRequest, registry: MetamodelRegistry) -> EvaluationRequest:
    advance_agent = None
    if body.advance_agent_key is not None:
        if body.advance_agent_key not in registry.agents:
            raise UnknownAgentError(body.advance_agent_key)
        advance_agent = registry.agents[body.advance_agent_key]  # the real object, mutated in place
    return EvaluationRequest(
        suite_key=body.suite_key,
        subject_ref=body.subject_ref,
        observed_values=body.observed_values,
        evidence_refs=body.evidence_refs,
        component_versions=body.component_versions,
        evaluated_at=body.evaluated_at,
        advance_agent=advance_agent,
        advance_to=body.advance_to,
    )


def build_gate_request(gate_key: str, body: GateAssessRequest) -> GateRequest:
    return GateRequest(
        gate_key=gate_key,
        present_artifact_kinds=body.present_artifact_kinds,
        checklist_outcomes=body.checklist_outcomes,
        satisfied_evidence=body.satisfied_evidence,
        approvals=body.approvals,
        evaluation_subject_ref=body.evaluation_subject_ref,
    )


def build_llm_client(backend: str, agent_key: str, task: str, fixtures_dir: Path | None) -> AgentLLMClient:
    if backend == "replay":
        if fixtures_dir is None:
            raise ReplayBackendUnavailableError()
        return ReplayAgentClient(fixtures_dir, agent_key=agent_key, task=task)
    if backend == "anthropic":
        return AnthropicAgentClient()
    if backend == "copilot_cli":
        return CopilotCliAgentClient()
    raise AssertionError(f"unreachable -- Literal type already constrained backend to a known value, got {backend!r}")


def build_agent_run_request(
    body: AgentRunHttpRequest, registry: MetamodelRegistry, agent_fixtures_dir: Path | None
) -> AgentRunRequest:
    if body.agent_key not in registry.agents:
        raise UnknownAgentError(body.agent_key)
    return AgentRunRequest(
        agent_key=body.agent_key,
        task=body.task,
        llm_client=build_llm_client(body.llm_backend, body.agent_key, body.task, agent_fixtures_dir),
        tool_executor=SimulatedToolExecutor(),  # never configurable -- see module docstring
        context_policy=body.context_policy,
        approval_policy=AutomationLevelApprovalPolicy(
            automation_level=body.automation_level, granted=body.granted_approval
        ),
        max_iterations=body.max_iterations,
    )


def build_workflow_llm_client(config: WorkflowLiveBackendConfig) -> AgentLLMClient:
    """`AgentCoreHarnessClient` is the one backend the other three
    (`build_llm_client`) don't cover -- added here rather than folded into
    that function, since a workflow's `WorkflowLiveBackendConfig` is a
    different request shape (`harness_arn`/`qualifier`/`model_id`) from
    `AgentRunHttpRequest`'s plain `llm_backend` string."""
    if config.llm_backend == "agentcore":
        return AgentCoreHarnessClient(
            harness_arn=config.harness_arn or "",
            qualifier=config.qualifier,
            model_id=config.model_id,
        )
    if config.llm_backend == "anthropic":
        return AnthropicAgentClient(model=config.anthropic_model) if config.anthropic_model else AnthropicAgentClient()
    if config.llm_backend == "copilot_cli":
        return CopilotCliAgentClient()
    raise AssertionError(f"unreachable -- Literal type already constrained backend, got {config.llm_backend!r}")


def build_workflow_tool_executor(config: WorkflowLiveBackendConfig) -> ToolExecutor:
    """Real execution where `LocalToolExecutor` has one
    (git/pytest/github), `SimulatedToolExecutor` for everything else --
    matching `LocalToolExecutor`'s own documented fallback discipline
    rather than leaving those actions unusable in live mode."""
    return LocalToolExecutor(repo_path=config.repo_path, repo=config.repo, fallback=SimulatedToolExecutor())


def build_live_backends(body: WorkflowRunRequest, template: WorkflowTemplate) -> dict[str, LiveAgentBackend]:
    backends: dict[str, LiveAgentBackend] = {}
    for slot in template.agent_slots:
        config = body.live_agent_backends.get(slot.key) or body.live_backend
        if config is None:
            raise MissingWorkflowBackendError(slot.key)
        backends[slot.key] = LiveAgentBackend(
            llm_client=build_workflow_llm_client(config),
            tool_executor=build_workflow_tool_executor(config),
            automation_level=config.automation_level,
        )
    return backends


__all__ = [
    "build_agent_run_request",
    "build_evaluation_request",
    "build_gate_request",
    "build_live_backends",
    "build_llm_client",
    "build_workflow_llm_client",
    "build_workflow_tool_executor",
]
