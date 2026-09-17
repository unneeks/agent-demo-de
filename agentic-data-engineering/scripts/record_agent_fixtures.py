#!/usr/bin/env python3
"""Record a real golden session fixture for the agent runtime test suite.

Manual, one-time, never invoked by pytest. Requires a live backend
(`ANTHROPIC_API_KEY` by default) and real network access. Wraps whichever
real `AgentLLMClient` is selected in a recording proxy and runs a real
`run_agent()` session against a real worked agent and task -- so recording
exercises the exact same loop/dispatch/approval logic a real run would,
never a parallel reimplementation that could quietly drift from it. Tool
execution is always `SimulatedToolExecutor` -- recording never causes a
real side effect, matching this phase's "all tools simulated" scope.

Writes `tests/fixtures/agent_runtime/golden/<agent_key>__<slug(task)>.json`,
one commit-reviewable file per session. Regenerating a fixture is a
deliberate act with a diff a reviewer reads -- never a side effect of
running tests.

Usage:
    python scripts/record_agent_fixtures.py                       # Anthropic backend
    python scripts/record_agent_fixtures.py --backend copilot_cli
    python scripts/record_agent_fixtures.py --agent regression-agent \\
        --task "Summarize what a regression test suite should cover."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.base import utc_now  # noqa: E402
from domain.metamodel.enums import ApprovalLevel, AutomationLevel  # noqa: E402
from domain.metamodel.registry import MetamodelRegistry  # noqa: E402

from agent_runtime.approval import AutomationLevelApprovalPolicy  # noqa: E402
from agent_runtime.llm import AgentLLMClient, AgentTurnResult, ToolDefinition  # noqa: E402
from agent_runtime.loop import run_agent  # noqa: E402
from agent_runtime.replay_client import (  # noqa: E402
    AgentSessionFixture,
    RecordedTurn,
    build_task_hash,
    slug_for_task,
)
from agent_runtime.simulated_tools import SimulatedToolExecutor  # noqa: E402
from domain.metamodel.entities.shared.context import ContextPolicy  # noqa: E402

GOLDEN_FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "agent_runtime" / "golden"

DEFAULT_TASK = "Summarize what a regression test suite for a customer_360 pipeline should cover."


class RecordingAgentLLMClient:
    """Wraps a real `AgentLLMClient`; accumulates every turn, then writes
    one session fixture at the end -- a thin proxy, not a reimplementation.
    """

    def __init__(self, inner: AgentLLMClient, *, backend_name: str, agent_key: str, task: str) -> None:
        self._inner = inner
        self._backend_name = backend_name
        self._agent_key = agent_key
        self._task = task
        self._turns: list[RecordedTurn] = []
        self._tools: list[ToolDefinition] = []

    def next_turn(self, *, system_prompt: str, messages: list[dict[str, Any]], tools: list[ToolDefinition]) -> AgentTurnResult:
        if not self._tools:
            self._tools = tools
        result = self._inner.next_turn(system_prompt=system_prompt, messages=messages, tools=tools)
        self._turns.append(
            RecordedTurn(
                text=result.text,
                tool_calls=[
                    {"call_id": c.call_id, "tool_key": c.tool_key, "action_name": c.action_name, "input": c.input}
                    for c in result.tool_calls
                ],
                stop_reason=result.stop_reason,
            )
        )
        return result

    def write_fixture(self) -> Path:
        fixture = AgentSessionFixture(
            agent_key=self._agent_key,
            task_hash=build_task_hash(self._agent_key, self._task, self._tools),
            backend=self._backend_name,
            recorded_at=utc_now().isoformat(),
            turns=self._turns,
        )
        GOLDEN_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        path = GOLDEN_FIXTURES_DIR / f"{self._agent_key}__{slug_for_task(self._task)}.json"
        path.write_text(json.dumps(fixture.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def _build_client(backend: str) -> AgentLLMClient:
    if backend == "anthropic":
        from agent_runtime.anthropic_client import AnthropicAgentClient

        return AnthropicAgentClient()
    if backend == "copilot_cli":
        from agent_runtime.copilot_cli_client import CopilotCliAgentClient

        return CopilotCliAgentClient()
    raise ValueError(f"unknown backend {backend!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["anthropic", "copilot_cli"], default="anthropic")
    parser.add_argument("--agent", default="regression-agent")
    parser.add_argument("--task", default=DEFAULT_TASK)
    args = parser.parse_args()

    registry = MetamodelRegistry.load()
    if args.agent not in registry.agents:
        print(f"error: no agent {args.agent!r} in the catalog", file=sys.stderr)
        return 1

    real_client = _build_client(args.backend)
    recording_client = RecordingAgentLLMClient(
        real_client, backend_name=args.backend, agent_key=args.agent, task=args.task
    )

    policy = ContextPolicy(
        id="record-agent-fixtures",
        name="record-agent-fixtures",
        entity_type=ContextPolicy.model_fields["entity_type"].default,
        policy_key="record-agent-fixtures",
        max_tokens=100_000,
    )
    approval_policy = AutomationLevelApprovalPolicy(
        automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS, granted=ApprovalLevel.SAMPLED_QA
    )

    report = run_agent(
        registry.agents[args.agent],
        registry,
        args.task,
        llm_client=recording_client,
        tool_executor=SimulatedToolExecutor(),
        context_policy=policy,
        approval_policy=approval_policy,
    )

    path = recording_client.write_fixture()
    print(f"recorded {path.relative_to(REPO_ROOT)}")
    print(f"  turns: {len(report.turns)}, completed: {report.completed}, stop_reason: {report.stop_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
