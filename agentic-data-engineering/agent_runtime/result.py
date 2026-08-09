"""The shapes `run_agent` reports through -- itemized, never a boolean.

Mirrors `orchestrator.result`'s discipline: a denied or unresolved tool call
is a first-class, reportable outcome recorded on the report, never a silent
drop and never (by itself) a reason to abort the run -- the model sees the
denial/error as a synthetic tool result and can react to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.metamodel.entities.evaluation import Evidence

from agent_runtime.approval import ApprovalDecision


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call the model requested, and what actually happened to it."""

    call_id: str
    tool_key: str
    action_name: str
    input: dict[str, Any]
    approval: ApprovalDecision
    executed: bool
    output: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class AgentTurn:
    """One `AgentLLMClient.next_turn()` call and its resolved tool calls."""

    index: int
    text: str | None
    tool_calls: list[ToolCallRecord]
    stop_reason: str


@dataclass(frozen=True)
class AgentRunReport:
    """The outcome of one `run_agent()` call."""

    agent_key: str
    task: str
    turns: list[AgentTurn] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    completed: bool = False
    stop_reason: str = "max_iterations"
    context_bundle_hash: str | None = None
