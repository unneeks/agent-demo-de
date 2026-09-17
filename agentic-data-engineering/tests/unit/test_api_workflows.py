"""`/api/workflows` and `/workflows` -- starting and polling a workflow
run over real HTTP, through `TestClient`. `WorkflowRunner` itself is
exercised directly (threads, snapshots, approval) in
`tests/unit/test_workflow.py`; this file only proves the HTTP-level
translation and error handling."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

from webui.app import create_app  # noqa: E402

TEMPLATE_KEY = "data-engineering-sdlc"


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    return TestClient(create_app(registry, metadata, graph))


def _wait_for_completion(client: TestClient, run_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    snapshot = {}
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/workflows/{run_id}").json()
        if snapshot["status"] == "completed":
            return snapshot
        time.sleep(0.1)
    return snapshot


class TestStartDemoRun:
    def test_returns_a_run_id_and_an_initial_snapshot(self, client: TestClient) -> None:
        response = client.post("/api/workflows", json={"template_key": TEMPLATE_KEY, "mode": "demo"})

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "demo"
        assert body["run_id"]
        assert body["work_products_total"] == 28

    def test_the_run_can_be_polled_to_completion(self, client: TestClient) -> None:
        run_id = client.post("/api/workflows", json={"template_key": TEMPLATE_KEY, "mode": "demo"}).json()["run_id"]

        snapshot = _wait_for_completion(client, run_id)

        assert snapshot["status"] == "completed"
        assert snapshot["work_products_done"] == snapshot["work_products_total"]
        assert snapshot["total_tokens"] > 0

    def test_unknown_template_key_is_404(self, client: TestClient) -> None:
        response = client.post("/api/workflows", json={"template_key": "no-such-template", "mode": "demo"})
        assert response.status_code == 404


class TestStartLiveRun:
    def test_live_mode_without_any_backend_config_is_422(self, client: TestClient) -> None:
        response = client.post("/api/workflows", json={"template_key": TEMPLATE_KEY, "mode": "live"})
        assert response.status_code == 422

    def test_live_mode_with_an_unreachable_agentcore_harness_records_a_failed_slot(
        self, client: TestClient
    ) -> None:
        # No real AWS credentials/harness exist in this environment -- this
        # proves the HTTP plumbing wires a real AgentCoreHarnessClient in
        # (it fails at the actual boto3 call, not at request validation),
        # not that the call itself succeeds.
        response = client.post(
            "/api/workflows",
            json={
                "template_key": TEMPLATE_KEY,
                "mode": "live",
                "live_backend": {
                    "llm_backend": "agentcore",
                    "automation_level": "ASSISTED",
                    "harness_arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:harness/does-not-exist",
                },
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]

        deadline = time.monotonic() + 10.0
        snapshot = {}
        while time.monotonic() < deadline:
            snapshot = client.get(f"/api/workflows/{run_id}").json()
            if any(agent["status"] == "error" for agent in snapshot["agents"]):
                break
            time.sleep(0.1)
        assert any(agent["status"] == "error" for agent in snapshot["agents"])


class TestUnknownRun:
    def test_polling_an_unknown_run_is_404(self, client: TestClient) -> None:
        assert client.get("/api/workflows/does-not-exist").status_code == 404

    def test_approving_an_unknown_run_is_404(self, client: TestClient) -> None:
        response = client.post(
            "/api/workflows/does-not-exist/approve",
            json={"agent_slot_key": "data-analyst", "work_product_key": "x", "granted": "SINGLE_REVIEWER"},
        )
        assert response.status_code == 404


class TestHtmlRoutes:
    def test_list_workflows_page_renders(self, client: TestClient) -> None:
        response = client.get("/workflows")
        assert response.status_code == 200
        assert "Workflow dashboard" in response.text

    def test_starting_from_the_html_form_redirects_to_the_dashboard(self, client: TestClient) -> None:
        response = client.post("/workflows/start", data={"template_key": TEMPLATE_KEY}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/workflows/")

    def test_the_dashboard_page_renders_for_a_real_run(self, client: TestClient) -> None:
        run_id = client.post("/api/workflows", json={"template_key": TEMPLATE_KEY, "mode": "demo"}).json()["run_id"]

        response = client.get(f"/workflows/{run_id}")

        assert response.status_code == 200
        assert run_id in response.text

    def test_unknown_run_renders_error_html_not_json(self, client: TestClient) -> None:
        response = client.get("/workflows/does-not-exist")
        assert response.status_code == 404
        assert "application/json" not in response.headers["content-type"]
