"""`discover_project` -- four-pass ordering, error handling, and dangling
relationship skipping.

Driven by a `FakeExtractionClient` that returns a canned raw response per
file path (looked up the same way `ReplayExtractionClient` does, by parsing
the `File: ...` line), so these tests never touch the filesystem-fixture
golden set and stay independent of it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.metamodel.enums import EntityType
from discovery.errors import DiscoveryError
from discovery.extraction.replay_client import source_path_from_prompt
from discovery.orchestrate import discover_project
from discovery.result import DiscoveryReport
from project_graph.errors import IngestionError
from project_graph.service import ProjectGraphService

from tests.conftest import make_project


class FakeExtractionClient:
    """Routes by the source path embedded in every prompt's `File: ...` line."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses

    def extract(self, *, prompt: str, response_schema: dict) -> dict:
        path = source_path_from_prompt(prompt)
        if path not in self._responses:
            raise DiscoveryError(f"FakeExtractionClient has no canned response for {path!r}")
        return self._responses[path]


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo-repo"
    (repo / "models").mkdir(parents=True)
    (repo / "models" / "stg_customers.sql").write_text("select * from raw_customers")
    (repo / "seeds").mkdir()
    (repo / "seeds" / "raw_customers.csv").write_text("id,name\n1,a")
    (repo / "README.md").write_text("This project computes stg_customers from raw_customers.")
    return repo


PIPELINE_RESPONSE = {
    "entities": [
        {
            "entity_type": "Pipeline",
            "local_id": "p1",
            "suggested_id": "stg_customers",
            "pipeline_kind": "dbt_model",
            "confidence": 0.9,
        }
    ],
    "relationships": [
        {
            "type": "DEPENDS_ON",
            "source_local_id": "p1",
            "target_kind": "DataAsset",
            "target_symbolic_name": "raw_customers",
            "confidence": 0.85,
        }
    ],
}

ASSET_RESPONSE = {
    "entities": [
        {
            "entity_type": "DataAsset",
            "local_id": "a1",
            "suggested_id": "raw_customers",
            "asset_kind": "seed",
            "confidence": 0.9,
        }
    ],
    "relationships": [],
}


def _readme_response(target_id: str) -> dict:
    return {
        "entities": [
            {
                "entity_type": "DeliveryArtifact",
                "local_id": "doc",
                "suggested_id": "readme",
                "artifact_key": "readme",
                "artifact_kind": "project-readme",
                "confidence": 0.8,
            }
        ],
        "relationships": [
            {"type": "DESCRIBES", "source_local_id": "doc", "target_id": target_id, "confidence": 0.7}
        ],
    }


@pytest.fixture
def service(graph, metadata) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


class TestDiscoverProjectHappyPath:
    def test_all_four_passes_produce_a_coherent_report(self, tmp_path, registry, service) -> None:
        repo = _make_repo(tmp_path)
        client = FakeExtractionClient(
            {
                "models/stg_customers.sql": PIPELINE_RESPONSE,
                "seeds/raw_customers.csv": ASSET_RESPONSE,
                "README.md": _readme_response("stg_customers"),
            }
        )
        report = discover_project(
            service, registry, make_project("demo"), client, repository_root=repo, repository_id="demo-repo"
        )
        assert isinstance(report, DiscoveryReport)
        # Repository + Pipeline + DataAsset + DeliveryArtifact.
        assert report.entities_ingested == 4
        assert report.entities_by_type[EntityType.PIPELINE] == 1
        assert report.entities_by_type[EntityType.DATA_ASSET] == 1
        assert report.entities_by_type[EntityType.DELIVERY_ARTIFACT] == 1
        assert report.entities_by_type[EntityType.REPOSITORY] == 1
        # DEPENDS_ON (resolved) + DESCRIBES + 3 structural CONTAINS
        # (project->repo, repo->pipeline, repo->asset; DeliveryArtifact is not
        # a CONTAINS-legal target).
        assert report.relationships_ingested == 5
        assert report.failed == []
        assert report.skipped == []

    def test_report_project_ref_matches_the_registered_project(self, tmp_path, registry, service) -> None:
        repo = _make_repo(tmp_path)
        client = FakeExtractionClient(
            {
                "models/stg_customers.sql": PIPELINE_RESPONSE,
                "seeds/raw_customers.csv": ASSET_RESPONSE,
                "README.md": _readme_response("stg_customers"),
            }
        )
        report = discover_project(service, registry, make_project("demo"), client, repository_root=repo)
        assert report.project_ref.type is EntityType.PROJECT
        assert report.project_ref.id == "demo"


class TestUnresolvedRelationshipsAreSkippedNotFabricated:
    def test_a_relationship_naming_a_never_extracted_entity_is_skipped(
        self, tmp_path, registry, service
    ) -> None:
        repo = tmp_path / "demo-repo"
        (repo / "models").mkdir(parents=True)
        (repo / "models" / "stg_customers.sql").write_text("select * from raw_customers")
        client = FakeExtractionClient({"models/stg_customers.sql": PIPELINE_RESPONSE})

        report = discover_project(service, registry, make_project("demo"), client, repository_root=repo)

        assert report.entities_by_type[EntityType.PIPELINE] == 1
        assert EntityType.DATA_ASSET not in report.entities_by_type
        skip_kinds = {s.kind for s in report.skipped}
        assert "unresolved_relationship_target" in skip_kinds
        # Only the structural CONTAINS edges (project->repo, repo->pipeline)
        # were ingested -- DEPENDS_ON was never fabricated against a
        # never-extracted DataAsset.
        assert report.relationships_ingested == 2


class TestErrorHandlingModes:
    def test_collect_mode_records_a_schema_violation_and_continues(self, tmp_path, registry, service) -> None:
        repo = tmp_path / "demo-repo"
        (repo / "models").mkdir(parents=True)
        (repo / "models" / "broken.sql").write_text("select 1")
        (repo / "models" / "good.sql").write_text("select 1")
        client = FakeExtractionClient(
            {
                "models/broken.sql": {"entities": [{"entity_type": "Pipeline"}], "relationships": []},
                "models/good.sql": {
                    "entities": [
                        {
                            "entity_type": "Pipeline",
                            "local_id": "p1",
                            "suggested_id": "good",
                            "pipeline_kind": "dbt_model",
                            "confidence": 0.9,
                        }
                    ],
                    "relationships": [],
                },
            }
        )
        report = discover_project(
            service, registry, make_project("demo"), client, repository_root=repo, on_error="collect"
        )
        assert report.entities_by_type[EntityType.PIPELINE] == 1
        assert any(f.kind == "schema_violation" for f in report.failed)

    def test_fail_fast_mode_raises_on_the_first_extraction_failure(self, tmp_path, registry, service) -> None:
        repo = tmp_path / "demo-repo"
        (repo / "models").mkdir(parents=True)
        (repo / "models" / "broken.sql").write_text("select 1")
        client = FakeExtractionClient(
            {"models/broken.sql": {"entities": [{"entity_type": "Pipeline"}], "relationships": []}}
        )
        with pytest.raises(IngestionError):
            discover_project(
                service, registry, make_project("demo"), client, repository_root=repo, on_error="fail_fast"
            )


class TestEmptyRepository:
    def test_an_empty_repository_still_registers_project_and_repository(self, tmp_path, registry, service) -> None:
        repo = tmp_path / "empty-repo"
        repo.mkdir()
        client = FakeExtractionClient({})
        report = discover_project(service, registry, make_project("demo"), client, repository_root=repo)
        assert report.entities_by_type[EntityType.REPOSITORY] == 1
        assert report.entities_ingested == 1
        assert report.relationships_ingested == 1  # project -> repository CONTAINS
