"""GET /projects/{project_id}/gates/{gate_key} -- live GateReadiness via the
real, unmodified orchestrator.gate.assess_gate_readiness(). The honesty
banner text is asserted verbatim -- it must never silently regress."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from domain.metamodel.base import EntityRef  # noqa: E402
from domain.metamodel.enums import EntityType  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402
from project_graph.service import ProjectGraphService  # noqa: E402

from webui.app import create_app  # noqa: E402

from tests.conftest import make_evaluation, make_project  # noqa: E402

GATE_KEY = "gate.architecture-review"
SUITE_KEY = "architecture-quality-evaluation"


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestGateReadinessView:
    def test_unknown_project_is_404(self, client: TestClient) -> None:
        response = client.get(f"/projects/does-not-exist/gates/{GATE_KEY}")
        assert response.status_code == 404

    def test_unknown_gate_key_is_404(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        response = client.get("/projects/demo/gates/gate.does-not-exist")
        assert response.status_code == 404

    def test_readiness_renders_with_the_honesty_banner(self, service, client: TestClient) -> None:
        service.register_project(make_project("demo"))
        evaluation = make_evaluation(
            "eval-1",
            suite_key=SUITE_KEY,
            subject_ref=EntityRef(type=EntityType.DELIVERY_ARTIFACT, id="solution-architecture-v1"),
        )
        service.ingest_entity(evaluation)

        response = client.get(f"/projects/demo/gates/{GATE_KEY}")
        assert response.status_code == 200
        assert (
            "ARTIFACTS, CHECKLISTS, EVIDENCE and APPROVALS are always assessed against"
            in response.text
        )
        assert "EVALUATIONS" in response.text
        assert "TRACEABILITY" in response.text
        assert "passed_evaluation_keys" in response.text
        assert "service.assess_traceability" in response.text
