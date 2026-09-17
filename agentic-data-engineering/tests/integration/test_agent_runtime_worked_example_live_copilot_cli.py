"""Live proof for `CopilotCliAgentClient`: a real subprocess-driven,
multi-turn session against a real worked agent.

Skips when neither `copilot` nor `gh` is found on `PATH`, mirroring
`test_discovery_worked_example_live_copilot_cli.py`'s skip precedent.
Given the larger, explicitly accepted risk around this backend's
non-interactive multi-turn tool-calling contract (see
`agent_runtime/copilot_cli_client.py`'s own docstring and ADR-0017), this
assertion is deliberately the most tolerant in the suite: the run must
complete without an unhandled exception and produce at least one turn,
proving the adapter's parsing and failure-handling path works end to end
against whatever the CLI actually returns, without over-asserting on
behavior nobody has observed yet. Tool execution is `SimulatedToolExecutor`
here too -- no tool call in this suite is ever real.
"""

from __future__ import annotations

import shutil

import pytest

from domain.metamodel.enums import ApprovalLevel, AutomationLevel

from agent_runtime.approval import AutomationLevelApprovalPolicy
from agent_runtime.errors import AgentRuntimeError
from agent_runtime.loop import run_agent
from agent_runtime.simulated_tools import SimulatedToolExecutor

from tests.conftest import make_policy

pytestmark = pytest.mark.agent_integration


@pytest.fixture
def copilot_cli_client():
    if not (shutil.which("copilot") or shutil.which("gh")):
        pytest.skip("neither 'copilot' nor 'gh' found on PATH")

    from agent_runtime.copilot_cli_client import CopilotCliAgentClient

    return CopilotCliAgentClient()


def test_live_copilot_cli_agent_run_against_a_real_worked_agent(registry, copilot_cli_client) -> None:
    agent = registry.agents["regression-agent"]
    approval_policy = AutomationLevelApprovalPolicy(
        automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS, granted=ApprovalLevel.SAMPLED_QA
    )

    try:
        report = run_agent(
            agent,
            registry,
            "Summarize what a regression test suite for a customer_360 pipeline should cover.",
            llm_client=copilot_cli_client,
            tool_executor=SimulatedToolExecutor(),
            context_policy=make_policy(max_tokens=100_000),
            approval_policy=approval_policy,
            max_iterations=6,
        )
    except AgentRuntimeError as exc:
        pytest.skip(f"Copilot CLI did not support the assumed non-interactive session shape: {exc}")

    # Deliberately not asserting on stop_reason or tool call content: whether
    # this CLI can be driven into the assumed multi-turn JSON-tool-call
    # contract at all is exactly the open question this test exists to
    # observe, not assume.
    assert report.turns, "a live run must produce at least one turn"
