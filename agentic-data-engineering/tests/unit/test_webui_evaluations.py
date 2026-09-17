"""GET /evaluations -- persisted Evaluation entities, optionally filtered."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.base import EntityRef  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_evaluation  # noqa: E402


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestEvaluationsListing:
    def test_no_evaluations_renders_empty_state(self, client: TestClient) -> None:
        response = client.get("/evaluations")
        assert response.status_code == 200
        assert "No evaluations found" in response.text

    def test_unfiltered_listing_shows_a_persisted_evaluation(
        self, metadata: InMemoryMetadataRepository, client: TestClient
    ) -> None:
        subject = EntityRef(type=EntityType.AGENT, id="regression-agent")
        evaluation = make_evaluation("eval-1", suite_key="s", subject_ref=subject)
        metadata.upsert(evaluation)

        response = client.get("/evaluations")
        assert response.status_code == 200
        assert "eval-1" in response.text or "Agent:regression-agent" in response.text

    def test_subject_filter_includes_matching_and_excludes_others(
        self, metadata: InMemoryMetadataRepository, client: TestClient
    ) -> None:
        match = make_evaluation(
            "eval-match", suite_key="s", subject_ref=EntityRef(type=EntityType.AGENT, id="regression-agent")
        )
        other = make_evaluation(
            "eval-other", suite_key="s", subject_ref=EntityRef(type=EntityType.AGENT, id="impact-analysis-agent")
        )
        metadata.upsert(match)
        metadata.upsert(other)

        response = client.get("/evaluations", params={"subject": "Agent:regression-agent"})
        assert response.status_code == 200
        assert "Agent:regression-agent" in response.text
        assert "impact-analysis-agent" not in response.text

    def test_malformed_subject_is_a_4xx_not_a_500(self, client: TestClient) -> None:
        response = client.get("/evaluations", params={"subject": "not-a-ref"})
        assert 400 <= response.status_code < 500
