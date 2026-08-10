"""`ReplayAgentClient` -- golden-fixture-backed, hermetic, fast.

A genuinely new fixture shape, not a straight copy of `discovery.extraction.
replay_client.ReplayExtractionClient`'s per-call request hash. That client
hashes every individual call's `(prompt, schema)` because each call is
independent and re-verifiable against its own source file. A multi-turn
session cannot be hashed that way: turn 3's `messages` already contains
turn 2's tool result, which came from `SimulatedToolExecutor`, not from an
external source -- hashing per-turn would make every fixture brittle to any
wording change in an intermediate canned tool response, for no real
staleness-detection benefit (there is nothing external a mid-session turn
could go stale against the way a source file can go stale).

So staleness is checked **once, at session start**, over `(agent_key, task,
tool catalog)` -- the only inputs that are genuinely external and could
drift. See docs/agent-runtime.md and ADR-0017.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_runtime.errors import AgentRuntimeError, FixtureExhaustedError
from agent_runtime.llm import AgentTurnResult
from agent_runtime.tools import ToolCallRequest, ToolDefinition
from discovery.hashing import sha256_text


def slug_for_task(task: str) -> str:
    """Human-navigable, diff-reviewable fixture filename fragment for one
    task string. Mirrors discovery.extraction.replay_client.slug_for_path's
    convention of a stable, readable stem rather than a raw hash."""
    return "".join(c if c.isalnum() else "-" for c in task.lower()).strip("-")[:80] or "task"


def build_task_hash(agent_key: str, task: str, tools: list[ToolDefinition]) -> str:
    """The staleness key: a hash over the opening state of a session --
    which agent, what task, and which tool catalog was offered -- not a
    per-turn hash. See module docstring for why."""
    canonical_tools = json.dumps(
        sorted(
            [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools],
            key=lambda t: t["name"],
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(agent_key + "\x00" + task + "\x00" + canonical_tools)


@dataclass(frozen=True)
class RecordedTurn:
    text: str | None
    tool_calls: list[dict[str, Any]]
    stop_reason: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RecordedTurn:
        return cls(
            text=data.get("text"),
            tool_calls=data.get("tool_calls", []),
            stop_reason=data["stop_reason"],
        )


@dataclass(frozen=True)
class AgentSessionFixture:
    agent_key: str
    task_hash: str
    backend: str
    recorded_at: str
    turns: list[RecordedTurn]

    def to_json(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "task_hash": self.task_hash,
            "backend": self.backend,
            "recorded_at": self.recorded_at,
            "turns": [
                {"text": t.text, "tool_calls": t.tool_calls, "stop_reason": t.stop_reason}
                for t in self.turns
            ],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AgentSessionFixture:
        return cls(
            agent_key=data["agent_key"],
            task_hash=data["task_hash"],
            backend=data["backend"],
            recorded_at=data["recorded_at"],
            turns=[RecordedTurn.from_json(t) for t in data["turns"]],
        )


class ReplayAgentClient:
    """Serves a committed golden session fixture instead of making a live
    call. Hermetic and fast: no network, no credentials, no external binary.
    """

    def __init__(self, fixtures_dir: Path, *, agent_key: str, task: str) -> None:
        self._fixtures_dir = fixtures_dir
        self._agent_key = agent_key
        self._task = task
        self._fixture: AgentSessionFixture | None = None
        self._turn_index = 0

    def _fixture_path(self) -> Path:
        return self._fixtures_dir / f"{self._agent_key}__{slug_for_task(self._task)}.json"

    def next_turn(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> AgentTurnResult:
        if self._fixture is None:
            self._fixture = self._load(tools)

        if self._turn_index >= len(self._fixture.turns):
            raise FixtureExhaustedError(
                f"session fixture for {self._agent_key!r}/{self._task!r} has "
                f"{len(self._fixture.turns)} recorded turns, but the loop asked for a "
                f"{self._turn_index + 1}th -- never repeats the last turn."
            )

        recorded = self._fixture.turns[self._turn_index]
        self._turn_index += 1
        tool_calls = [
            ToolCallRequest(
                call_id=call["call_id"],
                tool_key=call["tool_key"],
                action_name=call["action_name"],
                input=call.get("input", {}),
            )
            for call in recorded.tool_calls
        ]
        return AgentTurnResult(text=recorded.text, tool_calls=tool_calls, stop_reason=recorded.stop_reason)

    def _load(self, tools: list[ToolDefinition]) -> AgentSessionFixture:
        fixture_path = self._fixture_path()
        if not fixture_path.exists():
            raise AgentRuntimeError(
                f"no golden session fixture for agent {self._agent_key!r}, task "
                f"{self._task!r} at {fixture_path} -- run scripts/record_agent_fixtures.py"
            )
        fixture = AgentSessionFixture.from_json(json.loads(fixture_path.read_text(encoding="utf-8")))
        expected_hash = build_task_hash(self._agent_key, self._task, tools)
        if fixture.task_hash != expected_hash:
            raise AgentRuntimeError(
                f"golden session fixture for agent {self._agent_key!r}, task {self._task!r} is "
                "stale -- the agent's declared tools or the task text changed since recording. "
                "Rerun scripts/record_agent_fixtures.py."
            )
        return fixture


__all__ = [
    "AgentSessionFixture",
    "RecordedTurn",
    "ReplayAgentClient",
    "build_task_hash",
    "slug_for_task",
]
