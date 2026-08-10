"""The worked-example proof: `discover_project` against the real sibling
project (`agentic-ai-ollama-demo/`), driven entirely by committed golden
fixtures.

Hermetic and fast -- the one real agent call per file already happened once
(`scripts/record_extraction_fixtures.py`) and is committed under
`tests/fixtures/discovery/golden/`. Every number asserted here was verified
by an actual `discover_project` run against those fixtures, not hand-derived
-- see the golden fixtures themselves for the raw responses being replayed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.technical import Project
from domain.metamodel.enums import EntityType, ProvenanceState
from discovery.extraction.replay_client import ReplayExtractionClient
from discovery.orchestrate import discover_project

REPO_ROOT = Path(__file__).resolve().parents[2]
SIBLING_PROJECT = REPO_ROOT.parent / "agentic-ai-ollama-demo"
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "discovery" / "golden"

pytestmark = pytest.mark.skipif(
    not SIBLING_PROJECT.is_dir(), reason="agentic-ai-ollama-demo/ sibling project not present"
)


@pytest.fixture
def report(registry, graph, metadata):
    from project_graph.service import ProjectGraphService

    service = ProjectGraphService(metadata, graph)
    project = Project(
        id="ollama-demo",
        name="ollama-demo",
        entity_type=EntityType.PROJECT,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )
    client = ReplayExtractionClient(GOLDEN_DIR)
    return discover_project(
        service,
        registry,
        project,
        client,
        repository_root=SIBLING_PROJECT,
        repository_id="agentic-ai-ollama-demo",
    ), graph


class TestWorkedExampleEntityCounts:
    def test_six_pipelines_for_the_real_dbt_models(self, report) -> None:
        discovery_report, _ = report
        assert discovery_report.entities_by_type[EntityType.PIPELINE] == 6

    def test_four_seed_assets_each_with_a_schema_definition(self, report) -> None:
        discovery_report, _ = report
        assert discovery_report.entities_by_type[EntityType.DATA_ASSET] == 4
        assert discovery_report.entities_by_type[EntityType.SCHEMA_DEFINITION] == 4

    def test_five_infrastructure_entities_dockerfile_plus_four_compose_services(self, report) -> None:
        discovery_report, _ = report
        assert discovery_report.entities_by_type[EntityType.INFRASTRUCTURE] == 5

    def test_one_delivery_artifact_for_the_readme(self, report) -> None:
        discovery_report, _ = report
        assert discovery_report.entities_by_type[EntityType.DELIVERY_ARTIFACT] == 1

    def test_one_repository(self, report) -> None:
        discovery_report, _ = report
        assert discovery_report.entities_by_type[EntityType.REPOSITORY] == 1

    def test_total_entities_and_relationships_ingested(self, report) -> None:
        discovery_report, _ = report
        assert discovery_report.entities_ingested == 21
        assert discovery_report.relationships_ingested == 34
        assert discovery_report.failed == []


class TestWorkedExampleSkips:
    def test_dbt_project_yml_and_profiles_yml_are_skipped_not_extracted(self, report) -> None:
        """`yaml_config` has no legal target entity type today (see
        `SOURCE_KIND_ENTITY_TYPES`) -- these two files are walked and
        classified, but deliberately never sent to the agent."""
        discovery_report, _ = report
        skip_sources = {s.source for s in discovery_report.skipped}
        assert "dbt_demo/dbt_project.yml" in skip_sources
        assert "dbt_demo/profiles.yml" in skip_sources
        assert all(s.kind == "no_target_entity_type" for s in discovery_report.skipped)


class TestWorkedExampleDependsOnStructure:
    def test_mart_customer_360_depends_on_matches_the_real_ref_structure(self, report) -> None:
        _, graph_repo = report
        mart = EntityRef(type=EntityType.PIPELINE, id="mart_customer_360")
        edges = graph_repo.relationships(source=mart, type_="DEPENDS_ON")
        targets = {(edge.target.type, edge.target.id) for edge in edges}
        assert targets == {
            (EntityType.PIPELINE, "fct_account_activity"),
            (EntityType.PIPELINE, "stg_bank_loans"),
            (EntityType.PIPELINE, "stg_bank_customers"),
        }

    def test_transitive_traversal_from_the_mart_reaches_every_upstream_model_and_seed(
        self, report
    ) -> None:
        _, graph_repo = report
        start = EntityRef(type=EntityType.PIPELINE, id="mart_customer_360")
        result = graph_repo.traverse(start, relationship_types=["DEPENDS_ON"], direction="outgoing", max_depth=5)
        reached = {(r.ref.type, r.ref.id) for r in result}
        assert reached == {
            (EntityType.PIPELINE, "fct_account_activity"),
            (EntityType.PIPELINE, "stg_bank_accounts"),
            (EntityType.PIPELINE, "stg_bank_customers"),
            (EntityType.PIPELINE, "stg_bank_loans"),
            (EntityType.PIPELINE, "stg_bank_transactions"),
            (EntityType.DATA_ASSET, "bank_accounts"),
            (EntityType.DATA_ASSET, "bank_customers"),
            (EntityType.DATA_ASSET, "bank_loans"),
            (EntityType.DATA_ASSET, "bank_transactions"),
        }


class TestWorkedExampleDescribes:
    def test_readme_describes_every_bank_seed_and_the_customer_360_mart(self, report) -> None:
        _, graph_repo = report
        readme = EntityRef(type=EntityType.DELIVERY_ARTIFACT, id="readme.agentic-ai-ollama-demo")
        edges = graph_repo.relationships(source=readme, type_="DESCRIBES")
        targets = {(edge.target.type, edge.target.id) for edge in edges}
        assert targets == {
            (EntityType.DATA_ASSET, "bank_customers"),
            (EntityType.DATA_ASSET, "bank_accounts"),
            (EntityType.DATA_ASSET, "bank_transactions"),
            (EntityType.DATA_ASSET, "bank_loans"),
            (EntityType.PIPELINE, "mart_customer_360"),
        }
