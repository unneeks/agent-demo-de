"""Regression proof: adding `/api/*` (Phase 9) did not change `webui/`'s
six HTML routes' behavior. The existing `test_webui_*.py` files already
exercise each route's content in full and continue to pass unmodified
(same `create_app(registry, metadata, graph)` three-positional-argument
call, still valid with the new optional `agent_fixtures_dir` parameter) --
this file adds the one assertion those files couldn't have had before
Phase 9 existed: that the new prefix-aware `_error_handler` in
`webui/app.py` still renders `error.html` for the HTML routes and never
leaks a JSON envelope onto them, while the identical exception on `/api/*`
gets JSON, never `error.html`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

from webui.app import create_app  # noqa: E402


@pytest.fixture
def client(registry, metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> TestClient:
    # Same 3-positional-argument call every pre-Phase-9 test already makes --
    # the new agent_fixtures_dir parameter is optional and unused here.
    return TestClient(create_app(registry, metadata, graph))


class TestHtmlRoutesStillRenderHtmlOnError:
    def test_unknown_project_renders_error_html_not_json(self, client: TestClient) -> None:
        response = client.get("/projects/does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert "<html" in response.text.lower()

    def test_unknown_gate_renders_error_html_not_json(self, client: TestClient) -> None:
        response = client.get("/projects/does-not-exist/gates/gate.does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")


class TestApiRoutesGetJsonOnTheSameExceptionType:
    def test_unknown_project_returns_json_not_html(self, client: TestClient) -> None:
        response = client.get("/api/projects/does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["error"] == "UnknownProjectError"


class TestHtmlRoutesStillRenderSuccessfully:
    def test_home_page_still_renders(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_marketplace_page_still_renders(self, client: TestClient) -> None:
        response = client.get("/marketplace")
        assert response.status_code == 200
        assert "regression-agent" in response.text
