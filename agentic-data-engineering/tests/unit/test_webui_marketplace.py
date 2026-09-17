"""GET /marketplace -- catalog data plus real IMPLEMENTED_BY staffing edges."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.base import EntityRef  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from domain.metamodel.relationships import relationship  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

from webui.app import create_app  # noqa: E402


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestMarketplace:
    def test_real_agent_and_skill_appear(self, client: TestClient) -> None:
        response = client.get("/marketplace")
        assert response.status_code == 200
        assert "regression-agent" in response.text
        assert "repository-discovery" in response.text

    def test_staffing_edge_shows_the_agent_under_its_role(
        self, registry, graph: InMemoryGraphRepository, client: TestClient
    ) -> None:
        before = client.get("/marketplace")
        unstaffed_before = before.text.count("no agent has ever staffed this role")
        assert unstaffed_before == len(registry.engineering_roles)

        graph.upsert_relationship(
            relationship(
                "IMPLEMENTED_BY",
                EntityRef(type=EntityType.ENGINEERING_ROLE, id="regression-engineer"),
                EntityRef(type=EntityType.AGENT, id="regression-agent"),
                discovered_by="test",
            )
        )
        after = client.get("/marketplace")
        unstaffed_after = after.text.count("no agent has ever staffed this role")
        assert unstaffed_after == unstaffed_before - 1
