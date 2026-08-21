"""`run_agent()` end to end via `ReplayAgentClient` + `SimulatedToolExecutor`
-- normal completion, `max_iterations` cutoff, an approval-denied call the
model reacts to, and a hallucinated tool name."""

from __future__ import annotations

import json
from dataclasses import dataclass

from agent_runtime.approval import ApprovalDecision
from agent_runtime.llm import AgentTurnResult
from agent_runtime.loop import run_agent
from agent_runtime.replay_client import (
    AgentSessionFixture,
    RecordedTurn,
    ReplayAgentClient,
    build_task_hash,
    slug_for_task,
)
from agent_runtime.simulated_tools import SimulatedToolExecutor
from agent_runtime.tools import ToolCallRequest, build_tool_definitions
from domain.metamodel.enums import ApprovalLevel

from tests.conftest import make_policy


@dataclass(frozen=True)
class _Turn:
    text: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: str


class ScriptedClient:
    """A tiny, hand-rolled AgentLLMClient test double -- not the fixture
    replay path, so loop tests stay independent of the fixture format."""

    def __init__(self, turns: list[_Turn]) -> None:
        self._turns = turns
        self._index = 0

    def next_turn(self, *, system_prompt, messages, tools) -> AgentTurnResult:
        turn = self._turns[self._index]
        self._index += 1
        return AgentTurnResult(text=turn.text, tool_calls=turn.tool_calls, stop_reason=turn.stop_reason)


class AlwaysApprove:
    def decide(self, *, tool, action, registry) -> ApprovalDecision:
        return ApprovalDecision(required=ApprovalLevel.NONE, granted=ApprovalLevel.NONE, approved=True, reason="ok")


class AlwaysDeny:
    def decide(self, *, tool, action, registry) -> ApprovalDecision:
        return ApprovalDecision(
            required=ApprovalLevel.SINGLE_REVIEWER, granted=ApprovalLevel.NONE, approved=False, reason="no"
        )


class TestNormalCompletion:
    def test_a_tool_call_then_a_final_answer_completes(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        client = ScriptedClient(
            [
                _Turn(
                    text=None,
                    tool_calls=[ToolCallRequest(call_id="c1", tool_key="pytest", action_name="run_tests", input={})],
                    stop_reason="tool_use",
                ),
                _Turn(text="11/12 passed", tool_calls=[], stop_reason="end_turn"),
            ]
        )
        report = run_agent(
            agent,
            registry,
            "run the regression suite",
            llm_client=client,
            tool_executor=SimulatedToolExecutor(),
            context_policy=make_policy(max_tokens=100_000),
            approval_policy=AlwaysApprove(),
        )
        assert report.completed is True
        assert report.stop_reason == "end_turn"
        assert len(report.turns) == 2
        assert report.tool_calls[0].executed is True
        assert len(report.evidence) == 1
        assert report.evidence[0].evidence_kind == "test_result"


class TestMaxIterationsCutoff:
    def test_a_client_that_never_stops_is_cut_off(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        looping_turn = _Turn(
            text=None,
            tool_calls=[ToolCallRequest(call_id="c", tool_key="pytest", action_name="run_tests", input={})],
            stop_reason="tool_use",
        )
        client = ScriptedClient([looping_turn] * 10)
        report = run_agent(
            agent,
            registry,
            "loop forever",
            llm_client=client,
            tool_executor=SimulatedToolExecutor(),
            context_policy=make_policy(max_tokens=100_000),
            approval_policy=AlwaysApprove(),
            max_iterations=3,
        )
        assert report.completed is False
        assert report.stop_reason == "max_iterations"
        assert len(report.turns) == 3


class TestApprovalDeniedCallIsReactedTo:
    def test_denied_call_is_recorded_and_the_model_still_completes(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        client = ScriptedClient(
            [
                _Turn(
                    text=None,
                    tool_calls=[ToolCallRequest(call_id="c1", tool_key="pytest", action_name="run_tests", input={})],
                    stop_reason="tool_use",
                ),
                _Turn(text="cannot proceed without approval", tool_calls=[], stop_reason="end_turn"),
            ]
        )
        report = run_agent(
            agent,
            registry,
            "run the regression suite",
            llm_client=client,
            tool_executor=SimulatedToolExecutor(),
            context_policy=make_policy(max_tokens=100_000),
            approval_policy=AlwaysDeny(),
        )
        assert report.tool_calls[0].executed is False
        assert report.tool_calls[0].error is not None
        assert report.evidence == []  # a denied call produces no evidence
        assert report.completed is True


class TestRunAgentThroughTheRealReplayBackend:
    """The one end-to-end path through the real `ReplayAgentClient`, not the
    hand-rolled `ScriptedClient` -- proves `run_agent()` composes with the
    actual fixture-backed LLM client, not just a test double shaped like one."""

    def test_a_recorded_session_drives_a_full_run(self, registry, tmp_path) -> None:
        agent = registry.agents["regression-agent"]
        task = "run the regression suite"
        tools = build_tool_definitions(agent, registry)

        fixture = AgentSessionFixture(
            agent_key=agent.agent_key,
            task_hash=build_task_hash(agent.agent_key, task, tools),
            backend="anthropic",
            recorded_at="2026-08-09T00:00:00Z",
            turns=[
                RecordedTurn(
                    text=None,
                    tool_calls=[
                        {"call_id": "c1", "tool_key": "pytest", "action_name": "run_tests", "input": {}}
                    ],
                    stop_reason="tool_use",
                ),
                RecordedTurn(text="11/12 tests passed", tool_calls=[], stop_reason="end_turn"),
            ],
        )
        fixture_path = tmp_path / f"{agent.agent_key}__{slug_for_task(task)}.json"
        fixture_path.write_text(json.dumps(fixture.to_json()), encoding="utf-8")

        client = ReplayAgentClient(tmp_path, agent_key=agent.agent_key, task=task)
        report = run_agent(
            agent,
            registry,
            task,
            llm_client=client,
            tool_executor=SimulatedToolExecutor(),
            context_policy=make_policy(max_tokens=100_000),
            approval_policy=AlwaysApprove(),
        )
        assert report.completed is True
        assert report.stop_reason == "end_turn"
        assert report.tool_calls[0].executed is True


class TestHallucinatedToolNameIsReportedNotFatal:
    def test_unknown_tool_call_is_recorded_and_the_loop_continues(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        client = ScriptedClient(
            [
                _Turn(
                    text=None,
                    tool_calls=[ToolCallRequest(call_id="c1", tool_key="nonexistent", action_name="do_thing", input={})],
                    stop_reason="tool_use",
                ),
                _Turn(text="giving up", tool_calls=[], stop_reason="end_turn"),
            ]
        )
        report = run_agent(
            agent,
            registry,
            "run the regression suite",
            llm_client=client,
            tool_executor=SimulatedToolExecutor(),
            context_policy=make_policy(max_tokens=100_000),
            approval_policy=AlwaysApprove(),
        )
        assert report.tool_calls[0].executed is False
        assert "unknown tool action" in report.tool_calls[0].error
        assert report.completed is True
