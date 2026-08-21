"""Structural conformance of every `AgentLLMClient`/`ToolExecutor` backend
to its port.

Mirrors `tests/unit/test_extraction_ports.py`. Purely static (`inspect`), so
this never instantiates `AnthropicAgentClient` or `CopilotCliAgentClient` --
neither the `anthropic` package nor a `copilot`/`gh` binary is required for
this file to run.
"""

from __future__ import annotations

import inspect

from agent_runtime.anthropic_client import AnthropicAgentClient
from agent_runtime.copilot_cli_client import CopilotCliAgentClient
from agent_runtime.llm import AgentLLMClient
from agent_runtime.replay_client import ReplayAgentClient
from agent_runtime.simulated_tools import SimulatedToolExecutor
from agent_runtime.tools import ToolExecutor

LLM_ADAPTERS = [AnthropicAgentClient, CopilotCliAgentClient, ReplayAgentClient]


def _signature(func: object) -> list[tuple[str, object]]:
    signature = inspect.signature(func)  # type: ignore[arg-type]
    return [
        (name, parameter.kind)
        for name, parameter in signature.parameters.items()
        if name != "self"
    ]


class TestAgentLLMClientAdaptersConform:
    def test_protocol_declares_next_turn(self) -> None:
        assert callable(getattr(AgentLLMClient, "next_turn", None))

    def test_every_adapter_implements_next_turn(self) -> None:
        for adapter in LLM_ADAPTERS:
            assert callable(getattr(adapter, "next_turn", None)), f"{adapter.__name__} is missing next_turn()"

    def test_every_adapter_signature_matches_the_port(self) -> None:
        expected = _signature(AgentLLMClient.next_turn)
        for adapter in LLM_ADAPTERS:
            actual = _signature(adapter.next_turn)
            assert actual == expected, f"{adapter.__name__}.next_turn diverges from the port"

    def test_replay_client_satisfies_the_runtime_protocol_without_instantiating_live_clients(
        self, tmp_path
    ) -> None:
        client = ReplayAgentClient(tmp_path, agent_key="regression-agent", task="run tests")
        assert isinstance(client, AgentLLMClient)


class TestAdaptersDegradeGracefully:
    """Importing a live-backend adapter module must never require its
    driver (the `anthropic` package, a `copilot`/`gh` binary) to be present."""

    def test_anthropic_client_construction_without_an_api_key_fails_clearly(self, monkeypatch) -> None:
        from agent_runtime.errors import AgentRuntimeError

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        try:
            AnthropicAgentClient()
        except AgentRuntimeError as exc:
            assert "ANTHROPIC_API_KEY" in str(exc)
        else:
            raise AssertionError("expected AgentRuntimeError without an API key")

    def test_copilot_cli_client_construction_without_the_binary_fails_clearly(self, monkeypatch) -> None:
        from agent_runtime.errors import AgentRuntimeError

        monkeypatch.setattr("shutil.which", lambda name: None)
        try:
            CopilotCliAgentClient()
        except AgentRuntimeError as exc:
            assert "PATH" in str(exc)
        else:
            raise AssertionError("expected AgentRuntimeError without copilot/gh on PATH")


class TestToolExecutorConforms:
    def test_simulated_tool_executor_satisfies_the_runtime_protocol(self) -> None:
        assert isinstance(SimulatedToolExecutor(), ToolExecutor)
