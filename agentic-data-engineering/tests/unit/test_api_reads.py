"""GET /api/* -- JSON mirrors of webui/routes/*.py's six views."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.base import EntityRef  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from domain.metamodel.relationships import relationship  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_asset, make_evaluation, make_pipeline, make_project  # noqa: E402

MODEL_KEY = "de-delivery-model"
GATE_KEY = "gate.architecture-review"


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestListProjects:
    def test_registered_projects_are_listed(self, service, client: TestClient) -> None:
        service.register_project(make_project("alpha"))
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert any(p["id"] == "alpha" for p in response.json())


class TestProjectGraph:
    def test_unknown_project_is_404(self, client: TestClient) -> None:
        assert client.get("/api/projects/does-not-exist").status_code == 404

    def test_entities_and_relationships_appear(self, service, registry, client: TestClient) -> None:
        project = make_project("demo")
        service.register_project(project)
        pipeline = make_pipeline("stg_customers", "demo")
        asset = make_asset("customer_360", "demo")
        service.ingest_entity(pipeline)
        service.ingest_entity(asset)
        service.ingest_relationship(
            relationship("CONTAINS", project.ref(), pipeline.ref(), discovered_by="test"), registry
        )
        service.ingest_relationship(
            relationship("CONTAINS", project.ref(), asset.ref(), discovered_by="test"), registry
        )
        service.ingest_relationship(
            relationship("DEPENDS_ON", pipeline.ref(), asset.ref(), discovered_by="test"), registry
        )

        response = client.get("/api/projects/demo")
        assert response.status_code == 200
        body = response.json()
        pipeline_ids = [e["id"] for e in body["entities_by_type"].get("Pipeline", [])]
        assert "stg_customers" in pipeline_ids
        assert "DEPENDS_ON" in body["relationships_by_type"]


class TestDeliveryModel:
    def test_index_lists_the_worked_model(self, client: TestClient) -> None:
        response = client.get("/api/delivery-models")
        assert response.status_code == 200
        assert any(m["key"] == MODEL_KEY for m in response.json())

    def test_unknown_model_key_is_404(self, client: TestClient) -> None:
        assert client.get("/api/delivery-models/no-such-model").status_code == 404

    def test_detail_contains_real_phase_task_checklist_gate(self, client: TestClient) -> None:
        response = client.get(f"/api/delivery-models/{MODEL_KEY}")
        assert response.status_code == 200
        body = response.json()
        assert any(g["gate_key"] == GATE_KEY for g in body["gates"])
        assert any(p["phase"]["name"] == "Architecture" for p in body["phases"])


class TestMarketplace:
    def test_real_agent_and_skill_appear(self, client: TestClient) -> None:
        response = client.get("/api/marketplace")
        assert response.status_code == 200
        body = response.json()
        assert any(a["agent_key"] == "regression-agent" for a in body["agents"])
        assert any(s["skill_key"] == "repository-discovery" for s in body["skills"])


class TestEvaluations:
    def test_unfiltered_and_filtered_listing(self, metadata: InMemoryMetadataRepository, client: TestClient) -> None:
        match = make_evaluation(
            "eval-match", suite_key="s", subject_ref=EntityRef(type=EntityType.AGENT, id="regression-agent")
        )
        metadata.upsert(match)

        response = client.get("/api/evaluations")
        assert response.status_code == 200
        assert any(e["id"] == "eval-match" for e in response.json())

        filtered = client.get("/api/evaluations", params={"subject": "Agent:regression-agent"})
        assert filtered.status_code == 200
        assert len(filtered.json()) == 1

    def test_malformed_subject_is_422(self, client: TestClient) -> None:
        response = client.get("/api/evaluations", params={"subject": "not-a-ref"})
        assert response.status_code == 422


class TestGateReadinessRead:
    def test_unknown_gate_key_is_404(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.get("/api/projects/demo/gates/gate.does-not-exist")
        assert response.status_code == 404

    def test_reads_are_always_empty_state(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.get(f"/api/projects/demo/gates/{GATE_KEY}")
        assert response.status_code == 200
        body = response.json()
        artifacts_dim = next(d for d in body["dimensions"] if d["dimension"] == "ARTIFACTS")
        assert artifacts_dim["satisfied"] == 0
