"""`AnthropicAgentClient` -- calls the real Anthropic Messages API with
`tool_choice="auto"`, the multi-turn sibling of `discovery.extraction.
anthropic_client.AnthropicExtractionClient`'s single-forced-tool call.

Same lazy-import-of-`anthropic` and `ANTHROPIC_API_KEY`-or-explicit-`api_key`
constructor pattern as the extraction client, and the same implementation-time
risk, stated plainly rather than glossed over (see ADR-0013's precedent and
ADR-0017): the exact `tool_choice={"type": "auto"}` shape, `stop_reason`
values and content-block field names assumed here could not be verified
against live documentation from the environment this was written in. Treat
every constant below as a best-effort placeholder, not a confirmed fact --
check against real `anthropic` SDK docs before trusting this in production.
"""

from __future__ import annotations

import os
from typing import Any

from agent_runtime.errors import AgentRuntimeError
from agent_runtime.llm import AgentTurnResult
from agent_runtime.tools import ToolCallRequest, ToolDefinition

#: Unverified -- confirm the current recommended model id at implementation
#: time. Overridable via the constructor precisely because this is a guess.
DEFAULT_MODEL = "claude-sonnet-4-5"

#: Maps the real SDK's stop_reason values to the three this codebase
#: branches on. Anything unrecognized passes through unchanged so a real
#: divergence is visible rather than silently coerced.
_STOP_REASON_MAP = {
    "tool_use": "tool_use",
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "stop_sequence": "end_turn",
}


class AnthropicAgentClient:
    """Live multi-turn agent backend, calling the Anthropic Messages API."""

    def __init__(self, *, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise AgentRuntimeError(
                "no Anthropic API key: set ANTHROPIC_API_KEY or pass api_key= explicitly"
            )
        self._model = model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise AgentRuntimeError(
                    "the 'anthropic' package is not installed -- pip install -e '.[agent]'"
                ) from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def next_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> AgentTurnResult:
        client = self._ensure_client()
        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                tools=[
                    {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                    for t in tools
                ],
                tool_choice={"type": "auto"},
                messages=messages,
            )
        except Exception as exc:  # the real SDK's exception hierarchy is unverified here
            raise AgentRuntimeError(f"Anthropic Messages API call failed: {exc}") from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in message.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_calls.append(_tool_call_from_block(block))

        stop_reason = _STOP_REASON_MAP.get(message.stop_reason, message.stop_reason)
        return AgentTurnResult(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw={"id": getattr(message, "id", ""), "stop_reason": message.stop_reason},
        )


def _tool_call_from_block(block: Any) -> ToolCallRequest:
    """A tool_use block's `name` is the LLM-facing 'tool__action' string --
    kept whole here and split by `resolve_tool_call` in loop.py, so this
    module stays ignorant of the catalog."""
    name = getattr(block, "name", "")
    tool_key, _, action_name = name.partition("__")
    return ToolCallRequest(
        call_id=getattr(block, "id", ""),
        tool_key=tool_key,
        action_name=action_name,
        input=dict(getattr(block, "input", {})),
    )


__all__ = ["AnthropicAgentClient", "DEFAULT_MODEL"]
