"""RUN AGENT: running an agent's declared skills against a real (simulated)
`ToolExecutor`, via `agent_runtime.run_agent()` -- the composition, not the
loop. Mirrors `orchestrator/staffing.py`'s shape exactly: the only new code
here is the wrap-and-link, `run_agent()` itself is untouched.

Never automatic: `run_cycle()` only runs the agents a caller explicitly
names via `agent_run_requests`, exactly as `evaluation_requests`/`gates` are
already caller-opt-in. Staffing produces catalog-level candidates; running
one is a separate, deliberate, potentially-costly act.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from agent_runtime.approval import ApprovalPolicy
from agent_runtime.llm import AgentLLMClient
from agent_runtime.loop import run_agent
from agent_runtime.tools import ToolExecutor
from domain.metamodel.entities.shared.context import ContextPolicy
from domain.metamodel.registry import MetamodelRegistry

from orchestrator.result import AgentRunOutcome, StaffingOutcome


@dataclass(frozen=True)
class AgentRunRequest:
    agent_key: str
    task: str
    llm_client: AgentLLMClient
    tool_executor: ToolExecutor
    context_policy: ContextPolicy
    approval_policy: ApprovalPolicy
    #: Optional link back to the SELECT AGENTS outcome that named this
    #: agent, so a caller can trace a run to the staffing decision behind it.
    staffing_outcome: StaffingOutcome | None = None
    max_iterations: int | None = None


def run_agents(
    registry: MetamodelRegistry, requests: Iterable[AgentRunRequest]
) -> list[AgentRunOutcome]:
    outcomes: list[AgentRunOutcome] = []
    for request in requests:
        agent = registry.agents[request.agent_key]
        report = run_agent(
            agent,
            registry,
            request.task,
            llm_client=request.llm_client,
            tool_executor=request.tool_executor,
            context_policy=request.context_policy,
            approval_policy=request.approval_policy,
            max_iterations=request.max_iterations,
        )
        outcomes.append(
            AgentRunOutcome(
                agent_key=request.agent_key,
                task=request.task,
                report=report,
                staffing_outcome=request.staffing_outcome,
            )
        )
    return outcomes


__all__ = ["AgentRunRequest", "run_agents"]
