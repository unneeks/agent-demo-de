"""GET /delivery-models and /delivery-models/{model_key} -- against the
real worked data-engineering delivery model."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

from webui.app import create_app  # noqa: E402

MODEL_KEY = "de-delivery-model"


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


class TestDeliveryModelIndex:
    def test_worked_model_is_listed(self, client: TestClient) -> None:
        response = client.get("/delivery-models")
        assert response.status_code == 200
        assert MODEL_KEY in response.text


class TestDeliveryModelDetail:
    def test_unknown_model_key_is_404(self, client: TestClient) -> None:
        response = client.get("/delivery-models/no-such-model")
        assert response.status_code == 404

    def test_real_phase_task_checklist_and_gate_appear(self, client: TestClient) -> None:
        response = client.get(f"/delivery-models/{MODEL_KEY}")
        assert response.status_code == 200
        assert "Architecture" in response.text
        assert "task.solution-architecture" in response.text
        assert "architecture-checklist" in response.text
        assert "gate.architecture-review" in response.text
