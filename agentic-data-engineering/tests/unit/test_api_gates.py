"""POST /api/projects/{project_id}/gates/{gate_key}/assess -- the one
endpoint that finally makes the four honesty-gap `GateState` fields real."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_project  # noqa: E402

GATE_KEY = "gate.architecture-review"


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestAssessGate:
    def test_unknown_project_is_404(self, client: TestClient) -> None:
        response = client.post(f"/api/projects/does-not-exist/gates/{GATE_KEY}/assess", json={})
        assert response.status_code == 404

    def test_unknown_gate_key_is_404(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post("/api/projects/demo/gates/gate.does-not-exist/assess", json={})
        assert response.status_code == 404

    def test_supplied_state_produces_a_different_reading_than_the_empty_get(
        self, service, client: TestClient
    ) -> None:
        service.register_project(make_project("demo"))

        empty = client.get(f"/api/projects/demo/gates/{GATE_KEY}")
        assert empty.status_code == 200
        empty_artifacts = next(d for d in empty.json()["dimensions"] if d["dimension"] == "ARTIFACTS")
        assert empty_artifacts["satisfied"] == 0

        supplied = client.post(
            f"/api/projects/demo/gates/{GATE_KEY}/assess",
            json={"present_artifact_kinds": ["solution-architecture"]},
        )
        assert supplied.status_code == 200
        supplied_artifacts = next(d for d in supplied.json()["dimensions"] if d["dimension"] == "ARTIFACTS")
        assert supplied_artifacts["satisfied"] == 1
