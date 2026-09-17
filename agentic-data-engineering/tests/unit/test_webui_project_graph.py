"""GET /projects/{project_id} -- one project's dual-twin graph state."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.relationships import relationship  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_asset, make_pipeline, make_project  # noqa: E402


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata, graph) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestProjectGraphView:
    def test_unknown_project_is_404(self, client: TestClient) -> None:
        response = client.get("/projects/does-not-exist")
        assert response.status_code == 404

    def test_entities_and_relationship_appear(self, service, registry, client: TestClient) -> None:
        project = make_project("demo")
        service.register_project(project)
        pipeline = make_pipeline("stg_customers", "demo")
        asset = make_asset("customer_360", "demo")
        service.ingest_entity(pipeline)
        service.ingest_entity(asset)
        # CONTAINS from the project is what makes an entity reachable from the
        # project's graph node at all -- project_ref is a plain field on the
        # entity, not a traversable edge (mirrors tests/unit/test_project_graph.py's
        # _seed() pattern).
        service.ingest_relationship(
            relationship("CONTAINS", project.ref(), pipeline.ref(), discovered_by="test"), registry
        )
        service.ingest_relationship(
            relationship("CONTAINS", project.ref(), asset.ref(), discovered_by="test"), registry
        )
        service.ingest_relationship(
            relationship("DEPENDS_ON", pipeline.ref(), asset.ref(), discovered_by="test"), registry
        )

        response = client.get("/projects/demo")
        assert response.status_code == 200
        assert "stg_customers" in response.text
        assert "customer_360" in response.text
        assert "DEPENDS_ON" in response.text
