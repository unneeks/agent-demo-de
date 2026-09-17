"""`AgentCoreHarnessClient` -- request/response shape tests against a
stubbed `bedrock-agentcore` boto3 client (no real AWS calls, no `boto3`
package required to run this file).

The request/response shapes tested here were read directly out of
`botocore`'s own `bedrock-agentcore` service model (see the module
docstring in `agent_runtime/agentcore_client.py`); this file's fake events
are built to match that model, not guessed independently.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_runtime.agentcore_client import AgentCoreHarnessClient
from agent_runtime.errors import AgentRuntimeError
from agent_runtime.tools import ToolDefinition

HARNESS_ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:harness/data-engineering-sdlc"


class _FakeAgentCoreClient:
    """Records every `invoke_harness` call and returns a scripted stream."""

    def __init__(self, streams: list[list[dict[str, Any]]]) -> None:
        self._streams = list(streams)
        self.calls: list[dict[str, Any]] = []

    def invoke_harness(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"stream": self._streams.pop(0)}


def _text_stream(text: str, *, input_tokens: int = 10, output_tokens: int = 5) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "end_turn"}},
        {
            "metadata": {
                "usage": {
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "totalTokens": input_tokens + output_tokens,
                },
                "metrics": {"latencyMs": 842},
            }
        },
    ]


def _tool_use_stream(tool_use_id: str, name: str, input_json: str) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {"toolUse": {"toolUseId": tool_use_id, "name": name}},
            }
        },
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": input_json}}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "tool_use"}},
        {
            "metadata": {
                "usage": {"inputTokens": 20, "outputTokens": 8, "totalTokens": 28},
                "metrics": {"latencyMs": 611},
            }
        },
    ]


TOOLS = [
    ToolDefinition(
        name="git__read_repository",
        description="Read repository files",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    )
]


class TestNextTurnTextOnly:
    def test_returns_text_and_no_tool_calls(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("all good")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        result = client.next_turn(system_prompt="be helpful", messages=[], tools=[])

        assert result.text == "all good"
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"

    def test_usage_and_latency_are_carried_through_raw(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("hi", input_tokens=100, output_tokens=40)])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        result = client.next_turn(system_prompt="x", messages=[], tools=[])

        assert result.raw["usage"] == {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140}
        assert result.raw["latency_ms"] == 842


class TestNextTurnToolUse:
    def test_extracts_one_tool_call_request(self) -> None:
        fake = _FakeAgentCoreClient([_tool_use_stream("tu-1", "git__read_repository", '{"path": "README.md"}')])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        result = client.next_turn(system_prompt="x", messages=[], tools=TOOLS)

        assert result.stop_reason == "tool_use"
        [call] = result.tool_calls
        assert call.call_id == "tu-1"
        assert call.tool_key == "git"
        assert call.action_name == "read_repository"
        assert call.input == {"path": "README.md"}

    def test_malformed_tool_input_json_does_not_raise(self) -> None:
        fake = _FakeAgentCoreClient([_tool_use_stream("tu-2", "git__read_repository", "{not json")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        result = client.next_turn(system_prompt="x", messages=[], tools=TOOLS)

        [call] = result.tool_calls
        assert call.input == {}


class TestRequestShape:
    def test_tools_are_advertised_as_inline_functions(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="x", messages=[], tools=TOOLS)

        [sent_tool] = fake.calls[0]["tools"]
        assert sent_tool == {
            "type": "inlineFunction",
            "name": "git__read_repository",
            "config": {
                "inlineFunction": {
                    "description": "Read repository files",
                    "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            },
        }

    def test_empty_tools_are_omitted_not_sent_as_an_empty_list(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="x", messages=[], tools=[])

        assert "tools" not in fake.calls[0]

    def test_model_is_omitted_when_no_model_id_given(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="x", messages=[], tools=[])

        assert "model" not in fake.calls[0]

    def test_model_is_sent_as_bedrock_config_when_model_id_given(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(
            harness_arn=HARNESS_ARN, model_id="anthropic.claude-sonnet", client=fake
        )

        client.next_turn(system_prompt="x", messages=[], tools=[])

        assert fake.calls[0]["model"] == {
            "bedrockModelConfig": {"modelId": "anthropic.claude-sonnet", "maxTokens": 4096}
        }

    def test_max_iterations_is_always_one(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="x", messages=[], tools=[])

        assert fake.calls[0]["maxIterations"] == 1

    def test_system_prompt_is_sent_as_a_content_block(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="you are helpful", messages=[], tools=[])

        assert fake.calls[0]["systemPrompt"] == [{"text": "you are helpful"}]


class TestMessageTranslation:
    def test_plain_string_user_content_becomes_a_text_block(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="x", messages=[{"role": "user", "content": "do the task"}], tools=[])

        assert fake.calls[0]["messages"] == [{"role": "user", "content": [{"text": "do the task"}]}]

    def test_assistant_tool_use_block_converts_to_harness_tool_use(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "checking"},
                    {"type": "tool_use", "id": "tu-1", "name": "git__read_repository", "input": {"path": "x"}},
                ],
            }
        ]

        client.next_turn(system_prompt="x", messages=messages, tools=[])

        [sent] = fake.calls[0]["messages"]
        assert sent["content"] == [
            {"text": "checking"},
            {"toolUse": {"toolUseId": "tu-1", "name": "git__read_repository", "input": {"path": "x"}}},
        ]

    def test_tool_result_block_converts_with_dict_content_as_json(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)
        messages = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "tu-1", "content": {"files": ["a.py"]}}],
            }
        ]

        client.next_turn(system_prompt="x", messages=messages, tools=[])

        [sent] = fake.calls[0]["messages"]
        assert sent["content"] == [{"toolResult": {"toolUseId": "tu-1", "content": [{"json": {"files": ["a.py"]}}]}}]


class TestSessionContinuity:
    def test_the_same_runtime_session_id_is_reused_across_calls(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("first"), _text_stream("second")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        client.next_turn(system_prompt="x", messages=[], tools=[])
        client.next_turn(system_prompt="x", messages=[], tools=[])

        first_session = fake.calls[0]["runtimeSessionId"]
        second_session = fake.calls[1]["runtimeSessionId"]
        assert first_session == second_session
        assert first_session  # non-empty

    def test_an_explicit_session_id_is_honored(self) -> None:
        fake = _FakeAgentCoreClient([_text_stream("ok")])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, session_id="run-42", client=fake)

        client.next_turn(system_prompt="x", messages=[], tools=[])

        assert fake.calls[0]["runtimeSessionId"] == "run-42"


class TestStreamErrors:
    def test_a_validation_exception_event_raises_agentruntimeerror(self) -> None:
        stream = [{"validationException": {"message": "bad request", "reason": "MALFORMED_INPUT"}}]
        fake = _FakeAgentCoreClient([stream])
        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=fake)

        with pytest.raises(AgentRuntimeError, match="bad request"):
            client.next_turn(system_prompt="x", messages=[], tools=[])


class TestInvokeFailure:
    def test_a_raised_exception_from_invoke_harness_is_wrapped(self) -> None:
        class _RaisingClient:
            def invoke_harness(self, **kwargs: Any) -> dict[str, Any]:
                raise RuntimeError("boom")

        client = AgentCoreHarnessClient(harness_arn=HARNESS_ARN, client=_RaisingClient())

        with pytest.raises(AgentRuntimeError, match="InvokeHarness call failed"):
            client.next_turn(system_prompt="x", messages=[], tools=[])
