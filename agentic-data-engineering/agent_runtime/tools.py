"""`ToolExecutor` -- one interface, multiple backends (ADR-0007's pattern,
proved out in Phase 3 by `ExtractionClient`).

Deliberately thin, mirroring `ExtractionClient.extract()`'s shape: one call
in (a tool, an action, an input dict), one dict out, no side effect the
caller didn't ask for. This phase ships exactly one concrete `ToolExecutor`
(`simulated_tools.SimulatedToolExecutor`) and no live backend at all -- see
`docs/agent-runtime.md`'s "what this is not". The Protocol still earns its
keep for the same three reasons ADR-0007 already gives: the contract is
self-documenting, a future phase adding a real backend is exactly the
swap-in the pattern exists for, and tests can substitute an alternate stub
(one that raises, one with overrides) without subclassing anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from domain.metamodel.entities.organization import Agent, Tool, ToolAction
from domain.metamodel.registry import MetamodelRegistry

from agent_runtime.errors import UnknownToolActionError


@dataclass(frozen=True)
class ToolCallRequest:
    """One tool call the model asked for, before it is resolved or gated."""

    call_id: str
    tool_key: str
    action_name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolDefinition:
    """One (tool, action) pair rendered into the LLM-facing tool-use shape."""

    name: str
    description: str
    input_schema: dict[str, Any]


@runtime_checkable
class ToolExecutor(Protocol):
    """Runs one catalog action, returns structured output. Never mutates the
    input, never raises for a normal domain-level failure (a canned backend
    returns whatever "this failed" looks like as data, not an exception --
    exceptions here are reserved for programming errors)."""

    def execute(self, *, tool: Tool, action: ToolAction, input: dict[str, Any]) -> dict[str, Any]:
        ...


def _llm_tool_name(tool_key: str, action_name: str) -> str:
    return f"{tool_key}__{action_name}"


def build_tool_definitions(agent: Agent, registry: MetamodelRegistry) -> list[ToolDefinition]:
    """Every action on every tool the agent declares, turned into a
    `ToolDefinition`. Not filtered to READ_ONLY -- the approval gate
    (`agent_runtime.approval`), not tool *availability*, is what stops a
    dangerous call, exactly as `docs/architecture.md`'s "High-risk actions
    need a human" governance table already frames the enforcement point."""
    definitions: list[ToolDefinition] = []
    for tool_key in agent.tools:
        tool = registry.tools.get(tool_key)
        if tool is None:
            continue
        for action in tool.actions:
            definitions.append(
                ToolDefinition(
                    name=_llm_tool_name(tool_key, action.name),
                    description=action.description or f"{tool.name}: {action.name}",
                    input_schema=action.input_schema or {"type": "object", "properties": {}},
                )
            )
    return definitions


def resolve_tool_call(name: str, registry: MetamodelRegistry) -> tuple[Tool, ToolAction]:
    """Splits an LLM-facing 'git__read_repository' name back into (Tool,
    ToolAction). Raises UnknownToolActionError for anything that doesn't
    resolve -- a model can hallucinate a tool name, and that must be a
    reportable, reactable failure, not a silent no-op."""
    tool_key, separator, action_name = name.partition("__")
    if not separator:
        raise UnknownToolActionError(f"malformed tool name {name!r}: expected 'tool__action'")
    tool = registry.tools.get(tool_key)
    if tool is None:
        raise UnknownToolActionError(f"no tool {tool_key!r} in the catalog")
    action = tool.action(action_name)
    if action is None:
        raise UnknownToolActionError(f"tool {tool_key!r} has no action {action_name!r}")
    return tool, action


__all__ = [
    "ToolCallRequest",
    "ToolDefinition",
    "ToolExecutor",
    "build_tool_definitions",
    "resolve_tool_call",
]
