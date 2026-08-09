"""GET / -- the registered-projects list."""

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
def client(registry, metadata, graph) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestProjectsList:
    def test_no_projects_renders_empty_state(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "No projects registered" in response.text

    def test_registered_projects_are_listed(self, service, client: TestClient) -> None:
        service.register_project(make_project("alpha"))
        service.register_project(make_project("beta"))
        response = client.get("/")
        assert response.status_code == 200
        assert "alpha" in response.text
        assert "beta" in response.text
