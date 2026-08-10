"""POST /api/projects/{project_id}/cycles."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_project  # noqa: E402

MODEL_KEY = "de-delivery-model"
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


class TestTriggerCycle:
    def test_unknown_delivery_model_key_is_404(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/cycles", json={"delivery_model_key": "no-such-model"}
        )
        assert response.status_code == 404

    def test_discovery_is_always_none(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post("/api/projects/demo/cycles", json={"delivery_model_key": MODEL_KEY})
        assert response.status_code == 200
        assert response.json()["discovery"] is None

    def test_composes_evaluation_and_gate_requests(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/cycles",
            json={
                "delivery_model_key": MODEL_KEY,
                "evaluation_requests": [
                    {
                        "suite_key": SUITE_KEY,
                        "subject_ref": {"type": "DeliveryArtifact", "id": "solution-architecture-v1"},
                        "observed_values": ARCHITECTURE_VALUES,
                    }
                ],
                "gates": [{"gate_key": "gate.architecture-review", "present_artifact_kinds": ["solution-architecture"]}],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["evaluations"]) == 1
        assert body["evaluations"][0]["evaluation"]["passed"] is True
        assert "gate.architecture-review" in body["gate_readiness"]

    def test_a_bad_nested_agent_key_4xxs_the_whole_request(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.post(
            "/api/projects/demo/cycles",
            json={
                "delivery_model_key": MODEL_KEY,
                "agent_run_requests": [
                    {
                        "agent_key": "does-not-exist",
                        "task": "x",
                        "llm_backend": "replay",
                        "automation_level": "SUPERVISED_AUTONOMOUS",
                        "context_policy": {
                            "id": "p", "name": "p", "entity_type": "ContextPolicy",
                            "policy_key": "p", "max_tokens": 1000,
                        },
                    }
                ],
            },
        )
        assert response.status_code == 404
