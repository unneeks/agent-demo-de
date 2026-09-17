"""POST /api/projects, /api/entities, /api/relationships."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.enums import EntityType  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

from webui.app import create_app  # noqa: E402


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


def _project_payload(project_id: str = "demo") -> dict:
    return {
        "id": project_id,
        "name": project_id,
        "entity_type": "Project",
        "provenance": "OBSERVED",
        "confidence": 1.0,
        "discovered_by": "test",
    }


class TestRegisterProject:
    def test_register_project_succeeds(self, client: TestClient, metadata: InMemoryMetadataRepository) -> None:
        response = client.post("/api/projects", json=_project_payload())
        assert response.status_code == 201
        assert response.json()["entity_id"] == "demo"
        assert metadata.get(EntityType.PROJECT, "demo") is not None  # the app used the same repo the test holds

    def test_project_registered_via_generic_entities_route_too(self, client: TestClient) -> None:
        response = client.post("/api/entities", json=_project_payload("via-entities"))
        assert response.status_code == 201
        assert response.json()["entity_id"] == "via-entities"


class TestIngestEntity:
    def test_unknown_entity_type_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/entities", json={"entity_type": "NotARealType"})
        assert response.status_code == 422

    def test_missing_entity_type_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/entities", json={"id": "x"})
        assert response.status_code == 422


class TestIngestRelationship:
    def test_relationship_between_registered_entities_succeeds(self, client: TestClient) -> None:
        client.post("/api/projects", json=_project_payload())
        pipeline = {
            "id": "stg_customers",
            "name": "stg_customers",
            "entity_type": "Pipeline",
            "provenance": "OBSERVED",
            "confidence": 1.0,
            "discovered_by": "test",
            "project_ref": {"type": "Project", "id": "demo"},
            "pipeline_kind": "dbt_model",
        }
        client.post("/api/entities", json=pipeline)

        response = client.post(
            "/api/relationships",
            json={
                "type": "CONTAINS",
                "source": {"type": "Project", "id": "demo"},
                "target": {"type": "Pipeline", "id": "stg_customers"},
                "provenance": "OBSERVED",
                "confidence": 1.0,
                "discovered_by": "test",
            },
        )
        assert response.status_code == 201
        assert response.json()["type"] == "CONTAINS"

    def test_illegal_relationship_type_pair_is_rejected(self, client: TestClient) -> None:
        client.post("/api/projects", json=_project_payload())
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
        assert response.status_code == 422
