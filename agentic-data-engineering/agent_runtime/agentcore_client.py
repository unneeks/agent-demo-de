"""`AgentCoreHarnessClient` -- the fourth `AgentLLMClient` backend, calling a
real agent "Harness" deployed in AWS Bedrock AgentCore via
`bedrock-agentcore`'s `InvokeHarness` operation.

Unlike `anthropic_client.py`/`copilot_cli_client.py` (whose exact SDK/CLI
shapes are stated as "unverified -- confirm against live docs"), the request
and response shapes assumed here were read directly out of the real,
installed `botocore` service model
(`botocore/data/bedrock-agentcore/2024-02-28/service-2.json`, botocore
1.43.95) rather than guessed -- see docs/workflow-dashboard.md and
ADR-0023. What is *not* verified is a live call against a real AWS account
or a real deployed Harness: no AWS credentials exist in the environment
this was written in, so the request/response parsing below is covered by
tests against a stubbed `boto3` client, not an end-to-end call.

`InvokeHarness`'s `messages` shape is Anthropic/Bedrock-Converse-style
content blocks (`role`, `content: [{text}|{toolUse}|{toolResult}]`) -- the
same shape `agent_runtime.loop.run_agent()`'s internal `messages` transcript
already uses for the Anthropic backend. That means this backend only has to
*translate* between the two content-block dialects; the multi-turn
tool-call-then-resume loop itself is `loop.py`'s existing, unmodified
`_dispatch()` + re-append-and-call-again logic (ADR-0017) -- exactly the
"harness returns a typed tool-call message, the orchestrator calls the
local function, then resumes the harness" flow the AgentCore integration
was asked to support, with zero new orchestration primitives.

One AgentCore-native mechanism replaces what would otherwise need a custom
JSON envelope: every catalog tool is advertised to the harness as a
`HarnessTool{type: "inlineFunction"}` -- AWS's own documented meaning for
that type is "When the agent calls this tool, the tool call is returned to
the caller for external execution," i.e. exactly what a local/developer-
machine tool call needs. No other Harness tool type (remoteMcp,
agentCoreBrowser, agentCoreGateway, agentCoreCodeInterpreter) is used here;
those execute inside AWS, which is not what a local `ToolExecutor` needs.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from agent_runtime.errors import AgentRuntimeError
from agent_runtime.llm import AgentTurnResult
from agent_runtime.tools import ToolCallRequest, ToolDefinition

#: `HarnessStopReason`'s real enum (service-2.json) mapped to the three
#: values `agent_runtime.loop` branches on. Anything unrecognized passes
#: through unchanged -- same discipline as `anthropic_client._STOP_REASON_MAP`.
_STOP_REASON_MAP = {
    "tool_use": "tool_use",
    "tool_result": "tool_use",
    "end_turn": "end_turn",
    "stop_sequence": "end_turn",
    "max_tokens": "max_tokens",
    "max_output_tokens_exceeded": "max_tokens",
}

#: `InvokeHarness` supports one internal agent-loop iteration per call
#: (`maxIterations`) before AgentCore would otherwise keep calling
#: AWS-hosted tools on its own. Every tool this backend advertises is
#: `inlineFunction` (control always returns to the caller), so `1` is the
#: value that makes one `invoke_harness()` call equal one `next_turn()`
#: turn -- matching the Protocol's "returns exactly one turn" contract.
_MAX_HARNESS_ITERATIONS = 1

#: Event keys that indicate the harness invocation itself failed, rather
#: than the model choosing not to call a tool.
_STREAM_ERROR_EVENTS = ("internalServerException", "validationException", "runtimeClientError")


class AgentCoreHarnessClient:
    """Live multi-turn agent backend, calling a Harness deployed in AWS
    Bedrock AgentCore.

    `harness_arn` is the only required identifier -- `model_id` is
    deliberately optional (unlike `AnthropicAgentClient.model`): a deployed
    Harness may already have its own default model configuration
    (`CreateHarness`/`CreateHarnessEndpoint`, a control-plane concern this
    backend never touches), and `InvokeHarness`'s own `model` field is
    optional for exactly that reason -- overriding it is opt-in, not
    required.
    """

    def __init__(
        self,
        *,
        harness_arn: str,
        qualifier: str | None = None,
        model_id: str | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
        region_name: str | None = None,
        session_id: str | None = None,
        runtime_user_id: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not harness_arn:
            raise AgentRuntimeError("AgentCoreHarnessClient requires a non-empty harness_arn")
        self._harness_arn = harness_arn
        self._qualifier = qualifier
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._region_name = region_name
        #: One client instance is scoped to one `run_agent()` call (the
        #: same lifetime `ReplayAgentClient` already has), so a single
        #: session id generated once and reused across every `next_turn()`
        #: call on this instance is "resume from where it left off" --
        #: `runtimeSessionId` is a *required* InvokeHarness field, not an
        #: optional nicety.
        self._session_id = session_id or str(uuid.uuid4())
        self._runtime_user_id = runtime_user_id
        #: Test seam: a caller (a unit test) can inject a stub client
        #: instead of a real boto3 one. Never used by production code,
        #: which always leaves this `None` and gets the lazily-constructed
        #: real client below.
        self._client: Any = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise AgentRuntimeError(
                    "the 'boto3' package is not installed -- pip install -e '.[agentcore]'"
                ) from exc
            # Deliberately no explicit credentials: the ambient boto3
            # default chain (env vars, ~/.aws/config or credentials via
            # `aws configure`/`aws sso login`, or IMDS) resolves whichever
            # identity is already logged in on this machine. This backend
            # must never accept or construct AWS keys itself.
            self._client = boto3.client("bedrock-agentcore", region_name=self._region_name)
        return self._client

    def next_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> AgentTurnResult:
        client = self._ensure_client()
        request: dict[str, Any] = {
            "harnessArn": self._harness_arn,
            "runtimeSessionId": self._session_id,
            "messages": [_to_harness_message(message) for message in messages],
            "systemPrompt": [{"text": system_prompt}],
            "maxIterations": _MAX_HARNESS_ITERATIONS,
        }
        if self._qualifier:
            request["qualifier"] = self._qualifier
        if self._runtime_user_id:
            request["runtimeUserId"] = self._runtime_user_id
        if tools:
            request["tools"] = [_to_harness_tool(tool) for tool in tools]
        if self._model_id:
            bedrock_model: dict[str, Any] = {"modelId": self._model_id, "maxTokens": self._max_tokens}
            if self._temperature is not None:
                bedrock_model["temperature"] = self._temperature
            request["model"] = {"bedrockModelConfig": bedrock_model}

        try:
            response = client.invoke_harness(**request)
        except Exception as exc:  # botocore's exception hierarchy varies by error type
            raise AgentRuntimeError(f"AgentCore InvokeHarness call failed: {exc}") from exc

        return _parse_harness_stream(response["stream"])


def _to_harness_message(message: dict[str, Any]) -> dict[str, Any]:
    return {"role": message.get("role", "user"), "content": _to_harness_content(message.get("content"))}


def _to_harness_content(content: Any) -> list[dict[str, Any]]:
    """`agent_runtime.loop`'s internal transcript entries are Anthropic-
    dialect content: a plain string, `None`, or a list of `{"type": ...}`
    blocks. Converts each to `HarnessContentBlock`'s field-name-discriminated
    union (`{"text": ...}` / `{"toolUse": {...}}` / `{"toolResult": {...}}`)."""
    if content is None:
        return []
    if isinstance(content, str):
        return [{"text": content}]
    blocks: list[dict[str, Any]] = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            blocks.append({"text": block.get("text", "")})
        elif block_type == "tool_use":
            blocks.append(
                {
                    "toolUse": {
                        "toolUseId": block["id"],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    }
                }
            )
        elif block_type == "tool_result":
            result_content = block.get("content")
            blocks.append(
                {
                    "toolResult": {
                        "toolUseId": block["tool_use_id"],
                        "content": _to_harness_tool_result_content(result_content),
                    }
                }
            )
        else:
            # Forward-compatible fallback: never silently drop a block
            # this converter doesn't yet recognize.
            blocks.append({"text": json.dumps(block)})
    return blocks


def _to_harness_tool_result_content(result_content: Any) -> list[dict[str, Any]]:
    if isinstance(result_content, dict):
        return [{"json": result_content}]
    return [{"text": str(result_content)}]


def _to_harness_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "inlineFunction",
        "name": tool.name,
        "config": {"inlineFunction": {"description": tool.description, "inputSchema": tool.input_schema}},
    }


def _parse_harness_stream(stream: Any) -> AgentTurnResult:
    text_parts: list[str] = []
    #: contentBlockIndex -> {"toolUseId", "name", "input_json"} -- tool
    #: input streams as raw JSON-text deltas (`HarnessToolUseBlockDelta.
    #: input` is a string), concatenated then parsed once the block stops.
    pending_tool_uses: dict[int, dict[str, str]] = {}
    stop_reason = "end_turn"
    usage: dict[str, Any] = {}
    latency_ms: int | None = None

    for event in stream:
        for error_key in _STREAM_ERROR_EVENTS:
            if error_key in event:
                message = event[error_key].get("message", error_key)
                raise AgentRuntimeError(f"AgentCore Harness stream error ({error_key}): {message}")

        if "contentBlockStart" in event:
            payload = event["contentBlockStart"]
            index = payload["contentBlockIndex"]
            tool_use = payload.get("start", {}).get("toolUse")
            if tool_use is not None:
                pending_tool_uses[index] = {
                    "toolUseId": tool_use["toolUseId"],
                    "name": tool_use["name"],
                    "input_json": "",
                }
        elif "contentBlockDelta" in event:
            payload = event["contentBlockDelta"]
            index = payload["contentBlockIndex"]
            delta = payload.get("delta", {})
            if "text" in delta:
                text_parts.append(delta["text"])
            elif "toolUse" in delta and index in pending_tool_uses:
                pending_tool_uses[index]["input_json"] += delta["toolUse"].get("input", "")
        elif "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason", stop_reason)
        elif "metadata" in event:
            metadata = event["metadata"]
            usage = metadata.get("usage", {})
            latency_ms = metadata.get("metrics", {}).get("latencyMs")

    tool_calls = [
        _tool_call_from_pending(index, pending) for index, pending in sorted(pending_tool_uses.items())
    ]
    return AgentTurnResult(
        text="".join(text_parts) if text_parts else None,
        tool_calls=tool_calls,
        stop_reason=_STOP_REASON_MAP.get(stop_reason, stop_reason),
        raw={"usage": _normalize_usage(usage), "latency_ms": latency_ms},
    )


def _normalize_usage(usage: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
        "total_tokens": usage.get("totalTokens", 0),
    }


def _tool_call_from_pending(index: int, pending: dict[str, str]) -> ToolCallRequest:
    name = pending["name"]
    tool_key, _, action_name = name.partition("__")
    try:
        tool_input = json.loads(pending["input_json"]) if pending["input_json"] else {}
    except json.JSONDecodeError:
        # A malformed streamed tool-input must not crash the whole run --
        # `resolve_tool_call()`/the approval gate downstream can still act
        # on an empty input, and the model can see the resulting error.
        tool_input = {}
    return ToolCallRequest(
        call_id=pending["toolUseId"],
        tool_key=tool_key,
        action_name=action_name,
        input=tool_input,
    )


__all__ = ["AgentCoreHarnessClient"]
