"""POST /api/projects/{project_id}/agent-runs -- all three llm_backend
values, including the replay-unconfigured 501."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agent_runtime.replay_client import AgentSessionFixture, RecordedTurn, build_task_hash, slug_for_task  # noqa: E402
from agent_runtime.tools import build_tool_definitions  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_project  # noqa: E402

AGENT_KEY = "regression-agent"
TASK = "run the regression suite"
CONTEXT_POLICY = {
    "id": "p",
    "name": "p",
    "entity_type": "ContextPolicy",
    "policy_key": "p",
    "max_tokens": 100_000,
}


def _request_body(**overrides) -> dict:
    body = {
        "agent_key": AGENT_KEY,
        "task": TASK,
        "llm_backend": "replay",
        "automation_level": "SUPERVISED_AUTONOMOUS",
        "granted_approval": "SAMPLED_QA",
        "context_policy": CONTEXT_POLICY,
    }
    body.update(overrides)
    return body


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))  # no agent_fixtures_dir


class TestUnknownAgent:
    def test_unknown_agent_key_is_404(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/agent-runs", json=_request_body(agent_key="does-not-exist")
        )
        assert response.status_code == 404


class TestReplayBackend:
    def test_unconfigured_replay_backend_is_501(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post("/api/projects/demo/agent-runs", json=_request_body())
        assert response.status_code == 501

    def test_configured_replay_backend_succeeds(
        self, service, registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository, tmp_path
    ) -> None:
        agent = registry.agents[AGENT_KEY]
        tools = build_tool_definitions(agent, registry)
        fixture = AgentSessionFixture(
            agent_key=AGENT_KEY,
            task_hash=build_task_hash(AGENT_KEY, TASK, tools),
            backend="anthropic",
            recorded_at="2026-08-09T00:00:00Z",
            turns=[RecordedTurn(text="11/12 tests passed", tool_calls=[], stop_reason="end_turn")],
        )
        fixture_path = tmp_path / f"{AGENT_KEY}__{slug_for_task(TASK)}.json"
        fixture_path.write_text(json.dumps(fixture.to_json()))

        service.register_project(make_project("demo"))
        client = TestClient(create_app(registry, metadata, graph, agent_fixtures_dir=tmp_path))
        response = client.post("/api/projects/demo/agent-runs", json=_request_body())
        assert response.status_code == 200
        body = response.json()
        assert body["report"]["completed"] is True
        assert body["report"]["stop_reason"] == "end_turn"


class TestAnthropicBackend:
    def test_missing_api_key_is_502(self, service, client: TestClient, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/agent-runs", json=_request_body(llm_backend="anthropic")
        )
        assert response.status_code == 502


class TestCopilotCliBackend:
    def test_missing_binary_is_502(self, service, client: TestClient, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda name: None)
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/agent-runs", json=_request_body(llm_backend="copilot_cli")
        )
        assert response.status_code == 502
