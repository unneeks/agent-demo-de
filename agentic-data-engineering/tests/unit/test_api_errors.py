"""One case per row of webui/app.py's exception -> status-code table,
asserting the JSON envelope shape (`error`/`detail`/`status_code`)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_project  # noqa: E402


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


def _assert_envelope(response, expected_status: int, expected_error: str) -> None:
    assert response.status_code == expected_status
    body = response.json()
    assert body["error"] == expected_error
    assert body["status_code"] == expected_status
    assert isinstance(body["detail"], str) and body["detail"]


class TestErrorEnvelope:
    def test_unknown_project_error(self, client: TestClient) -> None:
        _assert_envelope(client.get("/api/projects/nope"), 404, "UnknownProjectError")

    def test_unknown_gate_error(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        _assert_envelope(
            client.get("/api/projects/demo/gates/gate.nope"), 404, "UnknownGateError"
        )

    def test_unknown_delivery_model_error(self, client: TestClient) -> None:
        _assert_envelope(client.get("/api/delivery-models/nope"), 404, "UnknownDeliveryModelError")

    def test_unknown_agent_error(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/evaluations",
            json={
                "suite_key": "architecture-quality-evaluation",
                "subject_ref": {"type": "Agent", "id": "x"},
                "observed_values": {},
                "advance_agent_key": "nope",
            },
        )
        _assert_envelope(response, 404, "UnknownAgentError")

    def test_replay_backend_unavailable_error(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/agent-runs",
            json={
                "agent_key": "regression-agent",
                "task": "x",
                "llm_backend": "replay",
                "automation_level": "SUPERVISED_AUTONOMOUS",
                "context_policy": {
                    "id": "p", "name": "p", "entity_type": "ContextPolicy",
                    "policy_key": "p", "max_tokens": 1000,
                },
            },
        )
        _assert_envelope(response, 501, "ReplayBackendUnavailableError")

    def test_ingestion_error(self, service, registry, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/relationships",
            json={
                "type": "DEPENDS_ON",
                "source": {"type": "Project", "id": "demo"},
                "target": {"type": "CodeArtifact", "id": "x.sql"},
                "provenance": "OBSERVED",
                "confidence": 1.0,
                "discovered_by": "test",
            },
        )
        _assert_envelope(response, 422, "IngestionError")

    def test_key_error_fallback(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/evaluations",
            json={
                "suite_key": "no-such-suite",
                "subject_ref": {"type": "Agent", "id": "regression-agent"},
                "observed_values": {},
            },
        )
        _assert_envelope(response, 404, "KeyError")
