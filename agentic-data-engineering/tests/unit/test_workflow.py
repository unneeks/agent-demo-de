"""`orchestrator.workflow` -- template loading/validation, and the
`WorkflowRunner` end to end in both modes.

Demo mode is exercised as a real, complete run (it needs no credentials).
Live mode is exercised against a fake `AgentLLMClient` (this environment
has no live AWS/Anthropic credentials) -- proving `WorkflowRunner` drives
the real, unmodified `agent_runtime.loop.run_agent()` correctly, not that
any particular backend's wire format is correct (that's
`test_agentcore_client.py`'s job).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from agent_runtime.errors import AgentRuntimeError
from agent_runtime.llm import AgentTurnResult
from agent_runtime.simulated_tools import SimulatedToolExecutor
from agent_runtime.tools import ToolCallRequest
from domain.metamodel.enums import ApprovalLevel, AutomationLevel
from orchestrator.workflow import (
    LiveAgentBackend,
    WorkflowTemplateError,
    load_workflow_templates,
    start_workflow_run,
)


def _wait_until_settled(runner, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while runner.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)


class _StaticClient:
    """Always ends the turn immediately -- no tool calls, nothing to deny."""

    def next_turn(self, *, system_prompt, messages, tools):
        return AgentTurnResult(text="done", tool_calls=[], stop_reason="end_turn")


class _DeniedOnceClient:
    """Requests a tool call that always needs more approval than granted
    on its first call for a given work product's `run_agent()` call, then
    ends cleanly -- so a retry with elevated approval succeeds."""

    def next_turn(self, *, system_prompt, messages, tools):
        # A fresh run_agent() call always starts with exactly one message
        # (the task) -- so "first turn of this call" is "len(messages) == 1".
        if len(messages) == 1:
            return AgentTurnResult(
                text=None,
                tool_calls=[
                    ToolCallRequest(
                        call_id="c1",
                        tool_key="github",
                        action_name="comment_on_pull_request",
                        input={"number": 1, "body": "x"},
                    )
                ],
                stop_reason="tool_use",
            )
        return AgentTurnResult(text="done", tool_calls=[], stop_reason="end_turn")


class TestLoadWorkflowTemplates:
    def test_loads_the_real_data_engineering_sdlc_template(self, registry) -> None:
        templates = load_workflow_templates(registry)

        template = templates["data-engineering-sdlc"]
        assert [p.key for p in template.phases] == ["requirements", "design", "build", "test", "release"]
        assert {slot.key for slot in template.agent_slots} == {
            "data-analyst",
            "data-engineer",
            "test-engineer",
            "release-lead",
        }

    def test_every_agent_slot_names_a_real_registered_agent(self, registry) -> None:
        templates = load_workflow_templates(registry)
        template = templates["data-engineering-sdlc"]
        for slot in template.agent_slots:
            assert slot.agent_key in registry.agents

    def test_unknown_agent_key_is_a_reportable_error_not_a_later_keyerror(self, registry, tmp_path) -> None:
        bad = tmp_path / "workflow_templates.yaml"
        bad.write_text(
            """
            workflow_templates:
              - key: broken
                name: Broken
                delivery_model_key: de-delivery-model
                phases:
                  - {key: p1, name: Phase One}
                agent_slots:
                  - key: s1
                    name: Slot One
                    agent_key: no-such-agent
                    mission: test
                    context_policy: {policy_key: workflow.test, max_tokens: 1000}
                    work_products:
                      - {key: wp1, name: WP One, phase_key: p1}
            """
        )
        with pytest.raises(WorkflowTemplateError, match="no-such-agent"):
            load_workflow_templates(registry, path=bad)

    def test_unknown_phase_key_on_a_work_product_is_a_reportable_error(self, registry, tmp_path) -> None:
        bad = tmp_path / "workflow_templates.yaml"
        bad.write_text(
            """
            workflow_templates:
              - key: broken
                name: Broken
                delivery_model_key: de-delivery-model
                phases:
                  - {key: p1, name: Phase One}
                agent_slots:
                  - key: s1
                    name: Slot One
                    agent_key: regression-agent
                    mission: test
                    context_policy: {policy_key: workflow.test, max_tokens: 1000}
                    work_products:
                      - {key: wp1, name: WP One, phase_key: no-such-phase}
            """
        )
        with pytest.raises(WorkflowTemplateError, match="no-such-phase"):
            load_workflow_templates(registry, path=bad)


class TestWorkflowRunnerDemoMode:
    def test_a_full_demo_run_completes_every_work_product(self, registry) -> None:
        template = load_workflow_templates(registry)["data-engineering-sdlc"]
        runner = start_workflow_run(run_id="demo-test", template=template, registry=registry, mode="demo")

        _wait_until_settled(runner)
        snapshot = runner.snapshot()

        assert snapshot.status == "completed"
        assert snapshot.work_products_done == snapshot.work_products_total
        assert snapshot.agents_active == 0
        assert all(phase["done"] == phase["total"] for phase in snapshot.phases)
        assert snapshot.total_tokens > 0
        assert snapshot.estimated_cost_usd > 0

    def test_recent_activity_is_populated_and_most_recent_first(self, registry) -> None:
        template = load_workflow_templates(registry)["data-engineering-sdlc"]
        runner = start_workflow_run(run_id="demo-test-2", template=template, registry=registry, mode="demo")

        _wait_until_settled(runner)
        snapshot = runner.snapshot()

        assert snapshot.recent_activity
        timestamps = [event["at"] for event in snapshot.recent_activity]
        assert timestamps == sorted(timestamps, reverse=True)


class TestWorkflowRunnerLiveMode:
    def test_requires_live_backends(self, registry) -> None:
        template = load_workflow_templates(registry)["data-engineering-sdlc"]
        with pytest.raises(AgentRuntimeError, match="live_backends"):
            start_workflow_run(run_id="x", template=template, registry=registry, mode="live", live_backends=None)

    def test_a_full_live_run_with_a_static_client_completes(self, registry) -> None:
        template = load_workflow_templates(registry)["data-engineering-sdlc"]
        backends = {
            slot.key: LiveAgentBackend(
                llm_client=_StaticClient(),
                tool_executor=SimulatedToolExecutor(),
                automation_level=AutomationLevel.ASSISTED,
            )
            for slot in template.agent_slots
        }
        runner = start_workflow_run(
            run_id="live-test", template=template, registry=registry, mode="live", live_backends=backends
        )

        _wait_until_settled(runner, timeout=10.0)
        snapshot = runner.snapshot()

        assert snapshot.status == "completed"
        assert snapshot.work_products_done == snapshot.work_products_total
        assert all(agent["status"] == "done" for agent in snapshot.agents)

    def test_a_denied_tool_call_pauses_the_slot_for_human_attention(self, registry) -> None:
        template = load_workflow_templates(registry)["data-engineering-sdlc"]
        backends = {
            slot.key: LiveAgentBackend(
                llm_client=_DeniedOnceClient(),
                tool_executor=SimulatedToolExecutor(),
                automation_level=AutomationLevel.ASSISTED,
            )
            for slot in template.agent_slots
        }
        runner = start_workflow_run(
            run_id="live-denied", template=template, registry=registry, mode="live", live_backends=backends
        )

        _wait_until_settled(runner, timeout=3.0)
        snapshot = runner.snapshot()

        assert snapshot.status == "running"
        data_analyst = next(a for a in snapshot.agents if a["key"] == "data-analyst")
        assert data_analyst["status"] == "waiting_for_approval"
        [item] = [h for h in snapshot.human_attention if h["agent_slot_key"] == "data-analyst"]
        assert "SINGLE_REVIEWER" in item["reason"]

    def test_approve_retries_with_elevated_approval_and_completes(self, registry) -> None:
        template = load_workflow_templates(registry)["data-engineering-sdlc"]
        backends = {
            slot.key: LiveAgentBackend(
                llm_client=_DeniedOnceClient(),
                tool_executor=SimulatedToolExecutor(),
                automation_level=AutomationLevel.ASSISTED,
            )
            for slot in template.agent_slots
        }
        runner = start_workflow_run(
            run_id="live-approve", template=template, registry=registry, mode="live", live_backends=backends
        )
        _wait_until_settled(runner, timeout=3.0)
        snapshot = runner.snapshot()
        [item] = [h for h in snapshot.human_attention if h["agent_slot_key"] == "data-analyst"]

        runner.approve("data-analyst", item["work_product_key"], granted=ApprovalLevel.SINGLE_REVIEWER)
        _wait_until_settled(runner, timeout=5.0)
        final = runner.snapshot()

        data_analyst = next(a for a in final.agents if a["key"] == "data-analyst")
        assert data_analyst["status"] == "done"
        assert all(wp["status"] == "completed" for wp in data_analyst["work_products"])
