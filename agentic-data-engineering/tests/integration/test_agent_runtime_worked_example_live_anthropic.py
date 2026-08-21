"""Live proof for `AnthropicAgentClient`: a real, multi-turn Messages API
conversation driving `run_agent()` for a real worked agent.

Skips without `ANTHROPIC_API_KEY`, mirroring
`test_discovery_worked_example_live_anthropic.py`'s skip precedent exactly.
Tool execution is `SimulatedToolExecutor` here too -- "live" describes the
LLM backend only; no tool call in this suite is ever real, matching the
user-approved scope for this phase (see docs/agent-runtime.md).

Asserts structural properties only (the run reaches a terminal stop_reason,
at least one turn happened, nothing crashed resolving the real catalog),
never exact transcript content -- a live model's wording is not
reproducible, only its shape is.
"""

from __future__ import annotations

import os

import pytest

from domain.metamodel.enums import ApprovalLevel, AutomationLevel

from agent_runtime.approval import AutomationLevelApprovalPolicy
from agent_runtime.loop import run_agent
from agent_runtime.simulated_tools import SimulatedToolExecutor

from tests.conftest import make_policy

pytestmark = pytest.mark.agent_integration


@pytest.fixture
def anthropic_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    try:
        import anthropic  # noqa: F401
    except ImportError:
        pytest.skip("anthropic package not installed (pip install -e '.[agent]')")

    from agent_runtime.anthropic_client import AnthropicAgentClient

    return AnthropicAgentClient()


def test_live_anthropic_agent_run_against_a_real_worked_agent(registry, anthropic_client) -> None:
    agent = registry.agents["regression-agent"]
    report = run_agent(
        agent,
        registry,
        "Summarize what a regression test suite for a customer_360 pipeline should cover.",
        llm_client=anthropic_client,
        tool_executor=SimulatedToolExecutor(),
        context_policy=make_policy(max_tokens=100_000),
        approval_policy=AutomationLevelApprovalPolicy(
            automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS, granted=ApprovalLevel.SAMPLED_QA
        ),
        max_iterations=6,
    )

    assert report.turns, "a live run must produce at least one turn"
    assert report.stop_reason in ("end_turn", "max_tokens", "max_iterations")
    # Every tool call the model actually made must have resolved against the
    # real catalog or been recorded as a denial/error -- never silently lost.
    assert len(report.tool_calls) == sum(len(t.tool_calls) for t in report.turns)
