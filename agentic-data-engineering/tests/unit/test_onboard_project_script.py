"""Unit coverage for `scripts/onboard_project.py`'s pure helpers.

The script itself is an interactive/live-I/O walkthrough (`input()`, live
discovery, optionally real Postgres/Neo4j) -- not something this suite runs
end to end. What's pure and testable without mocking any of that is factored
out; these tests cover exactly that factoring, mirroring
`tests/unit/test_schemas.py`'s `from scripts.<name> import ...` precedent.
"""

from __future__ import annotations

from domain.metamodel.enums import EntityType, ProvenanceState
from scripts.onboard_project import _find_extraction_backend, _parse_str_set, _project_from_answers


class TestParseStrSet:
    def test_splits_comma_separated(self) -> None:
        assert _parse_str_set("dbt, airflow ,snowflake") == {"dbt", "airflow", "snowflake"}

    def test_blank_is_empty_set(self) -> None:
        assert _parse_str_set("") == set()

    def test_drops_empty_items(self) -> None:
        assert _parse_str_set("dbt,, ,airflow") == {"dbt", "airflow"}


class TestProjectFromAnswers:
    def test_builds_a_real_project(self) -> None:
        project = _project_from_answers(
            project_id="acme",
            name="Acme Pipelines",
            technologies="dbt, snowflake",
            owners="data-platform",
            business_domain="retail",
            criticality="high",
        )
        assert project.id == "acme"
        assert project.entity_type is EntityType.PROJECT
        assert project.provenance is ProvenanceState.OBSERVED
        assert project.confidence == 1.0
        assert project.technologies == ["dbt", "snowflake"]
        assert project.owners == ["data-platform"]
        assert project.business_domain == "retail"
        assert project.criticality == "high"

    def test_blank_optional_fields_stay_none_and_empty(self) -> None:
        project = _project_from_answers(project_id="acme", name="Acme Pipelines")
        assert project.technologies == []
        assert project.owners == []
        assert project.business_domain is None
        assert project.criticality is None


class TestFindExtractionBackend:
    def test_only_anthropic_available(self) -> None:
        assert _find_extraction_backend(True, None) == "anthropic"

    def test_only_copilot_available(self) -> None:
        assert _find_extraction_backend(False, "copilot") == "copilot"

    def test_neither_available(self) -> None:
        assert _find_extraction_backend(False, None) is None

    def test_both_available_defers_to_caller(self) -> None:
        assert _find_extraction_backend(True, "copilot") is None
