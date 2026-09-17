"""`CopilotCliAgentClient` -- shells out to the GitHub Copilot CLI for a
multi-turn agent session.

A larger, differently-shaped risk than `AnthropicAgentClient`'s, and larger
still than `discovery.extraction.copilot_cli_client.CopilotCliExtractionClient`'s
already-flagged one: that client only ever needed one JSON object back from
one non-interactive call. This one needs the CLI to accept a rendered tool
catalog and a full transcript-so-far on every turn and hand back a turn's
worth of structured intent (`{"text": ..., "tool_calls": [...]}`) -- there is
no known documentation of a non-interactive, multi-turn, tool-calling
contract for this CLI. Stated as a known, accepted, larger risk in
ADR-0017, not silently designed around: if the real CLI cannot be driven
this way, this backend fails the same safe way a malformed Anthropic
response does -- an `AgentRuntimeError`, never a partially-trusted guess.

Reuses `_find_binary`'s PATH-lookup precedent from the extraction client
verbatim (same two candidate binaries, same "first one found wins" rule).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

from agent_runtime.errors import AgentRuntimeError
from agent_runtime.llm import AgentTurnResult
from agent_runtime.tools import ToolCallRequest, ToolDefinition

_CANDIDATE_BINARIES = ("copilot", "gh")
_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_TIMEOUT_SECONDS = 120


def _find_binary() -> str:
    for name in _CANDIDATE_BINARIES:
        found = shutil.which(name)
        if found:
            return name
    raise AgentRuntimeError(
        f"neither of {_CANDIDATE_BINARIES!r} was found on PATH -- install the GitHub Copilot CLI"
    )


def _render_tool_catalog(tools: list[ToolDefinition]) -> str:
    return json.dumps(
        [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools],
        sort_keys=True,
    )


def _render_transcript(system_prompt: str, messages: list[dict[str, Any]]) -> str:
    lines = [f"SYSTEM: {system_prompt}"]
    for message in messages:
        lines.append(f"{message.get('role', 'user').upper()}: {json.dumps(message.get('content', ''))}")
    return "\n".join(lines)


def _build_command(binary: str, prompt: str) -> list[str]:
    """The invocation shape assumed for a non-interactive, single-turn call
    within a longer session. Unverified against the real CLI -- see module
    docstring."""
    if binary == "copilot":
        return ["copilot", "-p", prompt]
    return ["gh", "copilot", "suggest", "-t", "shell", prompt]


def _extract_json_object(output: str) -> dict[str, Any]:
    match = _JSON_OBJECT_PATTERN.search(output)
    if match is None:
        raise AgentRuntimeError(
            "no JSON object found in Copilot CLI output -- the CLI may not support "
            "structured turn output in this invocation mode"
        )
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AgentRuntimeError(
            f"Copilot CLI output contained text that looked like JSON but did not parse: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise AgentRuntimeError(
            f"Copilot CLI output parsed as JSON but was a {type(parsed).__name__}, not an object"
        )
    return parsed


class CopilotCliAgentClient:
    """Live multi-turn agent backend, shelling out to the GitHub Copilot CLI.

    Each `next_turn()` call re-sends the full transcript-so-far plus the
    rendered tool catalog and requests one JSON object -- there is no
    session/conversation state kept by the CLI process between calls that
    this adapter can rely on, so every call is self-contained by design.
    """

    def __init__(self, *, binary: str | None = None) -> None:
        self._binary = binary or _find_binary()

    def next_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> AgentTurnResult:
        prompt = (
            f"{_render_transcript(system_prompt, messages)}\n\n"
            f"Available tools (call by name, 'tool__action'):\n{_render_tool_catalog(tools)}\n\n"
            "Respond with ONLY a single JSON object of the form "
            '{"text": "<your reasoning or final answer, or null>", '
            '"tool_calls": [{"call_id": "...", "name": "tool__action", "input": {...}}], '
            '"stop_reason": "tool_use" | "end_turn"}. No other text, no markdown code fence.'
        )
        command = _build_command(self._binary, prompt)
        try:
            completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
                command,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentRuntimeError(f"Copilot CLI invocation failed: {exc}") from exc

        if completed.returncode != 0:
            raise AgentRuntimeError(
                f"Copilot CLI exited {completed.returncode}: {completed.stderr.strip()[:500]}"
            )

        parsed = _extract_json_object(completed.stdout)
        tool_calls = [
            ToolCallRequest(
                call_id=call.get("call_id", ""),
                tool_key=call.get("name", "").partition("__")[0],
                action_name=call.get("name", "").partition("__")[2],
                input=call.get("input", {}),
            )
            for call in parsed.get("tool_calls", [])
        ]
        return AgentTurnResult(
            text=parsed.get("text"),
            tool_calls=tool_calls,
            stop_reason=parsed.get("stop_reason", "end_turn"),
            raw=parsed,
        )


__all__ = ["CopilotCliAgentClient"]
