"""`ReplayAgentClient` -- session-start-only staleness, missing fixture,
exhausted fixture. Mirrors `tests/unit/test_discovery_replay_client.py`'s
structure, adapted to a multi-turn session-shaped fixture."""

from __future__ import annotations

import json

import pytest

from agent_runtime.errors import AgentRuntimeError, FixtureExhaustedError
from agent_runtime.replay_client import (
    AgentSessionFixture,
    RecordedTurn,
    ReplayAgentClient,
    build_task_hash,
    slug_for_task,
)
from agent_runtime.tools import ToolDefinition

TOOLS = [ToolDefinition(name="pytest__run_tests", description="run tests", input_schema={})]


def _write_fixture(tmp_path, agent_key: str, task: str, turns: list[RecordedTurn]) -> None:
    fixture = AgentSessionFixture(
        agent_key=agent_key,
        task_hash=build_task_hash(agent_key, task, TOOLS),
        backend="anthropic",
        recorded_at="2026-08-09T00:00:00Z",
        turns=turns,
    )
    path = tmp_path / f"{agent_key}__{slug_for_task(task)}.json"
    path.write_text(json.dumps(fixture.to_json()), encoding="utf-8")


class TestServesRecordedTurnsInOrder:
    def test_two_turns_served_in_sequence(self, tmp_path) -> None:
        turns = [
            RecordedTurn(
                text=None,
                tool_calls=[{"call_id": "c1", "tool_key": "pytest", "action_name": "run_tests", "input": {}}],
                stop_reason="tool_use",
            ),
            RecordedTurn(text="done", tool_calls=[], stop_reason="end_turn"),
        ]
        _write_fixture(tmp_path, "regression-agent", "run tests", turns)
        client = ReplayAgentClient(tmp_path, agent_key="regression-agent", task="run tests")

        first = client.next_turn(system_prompt="sp", messages=[], tools=TOOLS)
        assert first.stop_reason == "tool_use"
        assert first.tool_calls[0].tool_key == "pytest"

        second = client.next_turn(system_prompt="sp", messages=[], tools=TOOLS)
        assert second.stop_reason == "end_turn"
        assert second.text == "done"


class TestMissingFixture:
    def test_missing_fixture_raises_clearly(self, tmp_path) -> None:
        client = ReplayAgentClient(tmp_path, agent_key="regression-agent", task="run tests")
        with pytest.raises(AgentRuntimeError, match="no golden session fixture"):
            client.next_turn(system_prompt="sp", messages=[], tools=TOOLS)


class TestStaleFixture:
    def test_different_tool_catalog_is_stale(self, tmp_path) -> None:
        _write_fixture(
            tmp_path,
            "regression-agent",
            "run tests",
            [RecordedTurn(text="done", tool_calls=[], stop_reason="end_turn")],
        )
        client = ReplayAgentClient(tmp_path, agent_key="regression-agent", task="run tests")
        different_tools = [ToolDefinition(name="git__read_repository", description="x", input_schema={})]
        with pytest.raises(AgentRuntimeError, match="stale"):
            client.next_turn(system_prompt="sp", messages=[], tools=different_tools)


class TestExhaustedFixture:
    def test_asking_for_a_turn_beyond_what_was_recorded_raises(self, tmp_path) -> None:
        _write_fixture(
            tmp_path,
            "regression-agent",
            "run tests",
            [RecordedTurn(text="done", tool_calls=[], stop_reason="end_turn")],
        )
        client = ReplayAgentClient(tmp_path, agent_key="regression-agent", task="run tests")
        client.next_turn(system_prompt="sp", messages=[], tools=TOOLS)
        with pytest.raises(FixtureExhaustedError):
            client.next_turn(system_prompt="sp", messages=[], tools=TOOLS)


class TestTaskHashIsStableAndOrderIndependent:
    def test_tool_order_does_not_affect_the_hash(self) -> None:
        a = ToolDefinition(name="git__read_repository", description="x", input_schema={})
        b = ToolDefinition(name="pytest__run_tests", description="y", input_schema={})
        assert build_task_hash("agent", "task", [a, b]) == build_task_hash("agent", "task", [b, a])

    def test_different_task_text_changes_the_hash(self) -> None:
        assert build_task_hash("agent", "task one", TOOLS) != build_task_hash("agent", "task two", TOOLS)
