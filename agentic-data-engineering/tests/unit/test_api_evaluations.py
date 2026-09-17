"""POST /api/projects/{project_id}/evaluations."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.enums import EntityType  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_project  # noqa: E402

SUITE_KEY = "architecture-quality-evaluation"
ARCHITECTURE_VALUES = {
    "nfr-coverage": 0.95,
    "integration-points-identified": 1.0,
    "vendor-neutral-justification": 0.9,
    "cost-estimate-completeness": 0.75,
}


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestTriggerEvaluation:
    def test_successful_run_persists_a_real_evaluation(
        self, service, metadata: InMemoryMetadataRepository, client: TestClient
    ) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/evaluations",
            json={
                "suite_key": SUITE_KEY,
                "subject_ref": {"type": "DeliveryArtifact", "id": "solution-architecture-v1"},
                "observed_values": ARCHITECTURE_VALUES,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["evaluation"]["passed"] is True
        assert metadata.list(EntityType.EVALUATION)

    def test_unknown_advance_agent_key_is_404(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/evaluations",
            json={
                "suite_key": SUITE_KEY,
                "subject_ref": {"type": "DeliveryArtifact", "id": "solution-architecture-v1"},
                "observed_values": ARCHITECTURE_VALUES,
                "advance_agent_key": "does-not-exist",
            },
        )
        assert response.status_code == 404

    def test_unknown_suite_key_is_a_clean_404_not_a_crash(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/evaluations",
            json={
                "suite_key": "no-such-suite",
                "subject_ref": {"type": "Agent", "id": "regression-agent"},
                "observed_values": {},
            },
        )
        assert response.status_code == 404
