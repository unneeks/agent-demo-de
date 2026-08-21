"""`AgentLLMClient` -- one interface, multiple real backends, extending
`ExtractionClient`'s "one interface, multiple real backends" pattern
(ADR-0007, proved out in Phase 3) from a single forced-tool one-shot call to
a free-choice, multi-turn one.

Deliberately returns *one turn*, not a whole conversation: turn
accumulation, `max_iterations`, tool dispatch and approval gating all live
in `agent_runtime.loop.run_agent()`, never inside a backend -- the direct
analogue of `ExtractionClient.extract()` never seeing `parse_response.py`'s
validation. This is what "extend the single-forced-tool pattern to
tool_choice='auto' with turn accumulation" concretely means: the
accumulation loop exists in exactly one place instead of being duplicated
across every backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agent_runtime.tools import ToolCallRequest, ToolDefinition

__all__ = ["AgentLLMClient", "AgentTurnResult", "ToolCallRequest", "ToolDefinition"]


@dataclass(frozen=True)
class AgentTurnResult:
    """One backend turn: whatever text the model produced, plus any tool
    calls it asked for. `stop_reason` is backend-normalized to one of
    "tool_use" | "end_turn" | "max_tokens" so `loop.py` never branches on a
    backend-specific string."""

    text: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: str
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AgentLLMClient(Protocol):
    """Turns one (system prompt, transcript, tool catalog) into one turn."""

    def next_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> AgentTurnResult:
        ...
