"""`run_agent()` -- the multi-turn planner-executor loop.

Turn accumulation, `max_iterations`, tool dispatch and approval gating all
live here, and only here -- no `AgentLLMClient` backend sees more than one
turn at a time (see `agent_runtime.llm`). Every tool call is answered by
whatever `ToolExecutor` the caller supplies; this phase always supplies
`SimulatedToolExecutor`, so no real side effect ever occurs regardless of
which LLM backend drives the loop. See docs/agent-runtime.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.metamodel.base import utc_now
from domain.metamodel.entities.evaluation import Evidence
from domain.metamodel.entities.organization import Agent
from domain.metamodel.entities.shared.context import ContextPolicy
from domain.metamodel.enums import ApprovalLevel, ProvenanceState
from domain.metamodel.registry import MetamodelRegistry

from agent_runtime.approval import ApprovalDecision, ApprovalPolicy
from agent_runtime.context import build_agent_context, render_system_prompt
from agent_runtime.errors import UnknownToolActionError
from agent_runtime.llm import AgentLLMClient
from agent_runtime.result import AgentRunReport, AgentTurn, ToolCallRecord
from agent_runtime.simulated_tools import EVIDENCE_KIND_BY_ACTION
from agent_runtime.tools import ToolCallRequest, ToolExecutor, build_tool_definitions

_DISCOVERED_BY = "agent_runtime@0.1.0"

#: Fed back to the model in place of a real tool result when a call is
#: denied or fails to resolve -- so the loop can genuinely react (try
#: something else, or stop) rather than the gate or the error being a
#: silent no-op the model never sees.
_DENIED_OUTPUT_KEY = "error"


def _dispatch(
    request: ToolCallRequest,
    *,
    agent: Agent,
    registry: MetamodelRegistry,
    tool_executor: ToolExecutor,
    approval_policy: ApprovalPolicy,
) -> ToolCallRecord:
    tool = registry.tools.get(request.tool_key)
    action = tool.action(request.action_name) if tool is not None else None
    if tool is None or action is None:
        denial = ApprovalDecision(
            required=ApprovalLevel.MAKER_CHECKER,
            granted=ApprovalLevel.NONE,
            approved=False,
            reason=f"unknown tool action: {request.tool_key}__{request.action_name}",
        )
        return ToolCallRecord(
            call_id=request.call_id,
            tool_key=request.tool_key,
            action_name=request.action_name,
            input=request.input,
            approval=denial,
            executed=False,
            error=str(UnknownToolActionError(denial.reason)),
        )

    decision = approval_policy.decide(tool=tool, action=action, registry=registry)
    if not decision.approved:
        return ToolCallRecord(
            call_id=request.call_id,
            tool_key=request.tool_key,
            action_name=request.action_name,
            input=request.input,
            approval=decision,
            executed=False,
            error=f"approval denied: requires {decision.required.value}, granted {decision.granted.value}",
        )

    output = tool_executor.execute(tool=tool, action=action, input=request.input)
    return ToolCallRecord(
        call_id=request.call_id,
        tool_key=request.tool_key,
        action_name=request.action_name,
        input=request.input,
        approval=decision,
        executed=True,
        output=output,
    )


def _evidence_for(record: ToolCallRecord, agent: Agent, now: datetime) -> Evidence | None:
    if not record.executed:
        return None
    evidence_kind = EVIDENCE_KIND_BY_ACTION.get((record.tool_key, record.action_name), "tool_output")
    return Evidence(
        id=f"evidence:{agent.agent_key}:{record.call_id}",
        name=f"{record.tool_key}.{record.action_name} result",
        entity_type=Evidence.model_fields["entity_type"].default,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=_DISCOVERED_BY,
        evidence_kind=evidence_kind,
        source_reference=f"tool://{record.tool_key}/{record.action_name}/{record.call_id}",
        subject_ref=agent.ref(),
        collected_at=now,
    )


def _tool_result_message(record: ToolCallRecord) -> dict[str, Any]:
    content = record.output if record.executed else {_DENIED_OUTPUT_KEY: record.error}
    return {
        "type": "tool_result",
        "tool_use_id": record.call_id,
        "content": content,
    }


def run_agent(
    agent: Agent,
    registry: MetamodelRegistry,
    task: str,
    *,
    llm_client: AgentLLMClient,
    tool_executor: ToolExecutor,
    context_policy: ContextPolicy,
    approval_policy: ApprovalPolicy,
    max_iterations: int | None = None,
    now: datetime | None = None,
) -> AgentRunReport:
    """Run one agent against one task to completion or `max_iterations`.

    One call, one agent, one task -- no scheduling, no daemon loop, no
    coordination with any other agent's run. `context_policy` and
    `approval_policy` are always caller-supplied, exactly as every other
    engine in this codebase takes its policy as an argument rather than
    reaching for a default it invents.
    """
    reference_time = now or utc_now()
    limit = max_iterations if max_iterations is not None else agent.max_iterations

    bundle = build_agent_context(agent, registry, task, policy=context_policy, now=reference_time)
    system_prompt = render_system_prompt(bundle, agent, task)
    tools = build_tool_definitions(agent, registry)

    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    turns: list[AgentTurn] = []
    all_tool_calls: list[ToolCallRecord] = []
    evidence: list[Evidence] = []
    completed = False
    stop_reason = "max_iterations"

    for index in range(limit):
        turn_result = llm_client.next_turn(system_prompt=system_prompt, messages=messages, tools=tools)
        stop_reason = turn_result.stop_reason

        records = [
            _dispatch(
                request,
                agent=agent,
                registry=registry,
                tool_executor=tool_executor,
                approval_policy=approval_policy,
            )
            for request in turn_result.tool_calls
        ]
        turns.append(AgentTurn(index=index, text=turn_result.text, tool_calls=records, stop_reason=stop_reason))
        all_tool_calls.extend(records)
        evidence.extend(item for record in records if (item := _evidence_for(record, agent, reference_time)) is not None)

        assistant_content: list[dict[str, Any]] = []
        if turn_result.text:
            assistant_content.append({"type": "text", "text": turn_result.text})
        assistant_content.extend(
            {
                "type": "tool_use",
                "id": record.call_id,
                "name": f"{record.tool_key}__{record.action_name}",
                "input": record.input,
            }
            for record in records
        )
        messages.append({"role": "assistant", "content": assistant_content or turn_result.text})

        if stop_reason != "tool_use" or not records:
            completed = stop_reason != "max_iterations" or not turn_result.tool_calls
            break

        messages.append({"role": "user", "content": [_tool_result_message(record) for record in records]})
    else:
        completed = False
        stop_reason = "max_iterations"

    return AgentRunReport(
        agent_key=agent.agent_key,
        task=task,
        turns=turns,
        tool_calls=all_tool_calls,
        evidence=evidence,
        completed=completed,
        stop_reason=stop_reason,
        context_bundle_hash=bundle.bundle_hash,
    )


__all__ = ["run_agent"]
