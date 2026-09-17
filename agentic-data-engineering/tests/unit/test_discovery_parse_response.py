"""The most important validation boundary in Phase 3.

A response that fails schema validation is rejected wholesale; within a
conforming response, a single malformed item fails only that item.
Nothing here is ever a partial write into the platform's own invariants --
every constructed entity/relationship still has to pass Pydantic
construction, on top of whatever the JSON Schema pass already caught.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType, ExtractionMethod, ProvenanceState
from discovery.extraction.parse_response import (
    DISCOVERED_BY,
    parse_delivery_response,
    parse_technical_response,
)
from discovery.extraction.prompts import (
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    KnownEntity,
    build_delivery_prompt,
    build_technical_prompt,
)

PROJECT_REF = EntityRef(type=EntityType.PROJECT, id="demo")


@pytest.fixture
def sql_prompt():
    return build_technical_prompt(relative_path=Path("models/p1.sql"), content="select 1", source_kind="sql")


class TestTechnicalResponseHappyPath:
    def test_valid_response_produces_a_provenanced_pipeline(self, sql_prompt) -> None:
        raw = {
            "entities": [
                {
                    "entity_type": "Pipeline",
                    "local_id": "p1",
                    "suggested_id": "stg_customers",
                    "pipeline_kind": "dbt_model",
                    "confidence": 0.95,
                }
            ],
            "relationships": [],
        }
        result = parse_technical_response(
            raw, prompt=sql_prompt, source_document="models/p1.sql", project_ref=PROJECT_REF
        )
        assert not result.failures
        [entity] = result.entities
        assert entity.id == "stg_customers"
        assert entity.name == "stg_customers"
        assert entity.entity_type is EntityType.PIPELINE
        assert entity.project_ref == PROJECT_REF
        assert entity.provenance is ProvenanceState.INFERRED
        assert entity.confidence == MAX_CONFIDENCE  # 0.95 clamped down to 0.90
        assert entity.discovered_by == DISCOVERED_BY
        assert entity.source_document == "models/p1.sql"
        assert entity.extraction_method is ExtractionMethod.SEMANTIC_EXTRACTION

    def test_confidence_is_clamped_at_the_floor_too(self, sql_prompt) -> None:
        raw = {
            "entities": [
                {
                    "entity_type": "Pipeline",
                    "local_id": "p1",
                    "suggested_id": "x",
                    "pipeline_kind": "dbt_model",
                    "confidence": 0.0,
                }
            ],
            "relationships": [],
        }
        result = parse_technical_response(
            raw, prompt=sql_prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert result.entities[0].confidence == MIN_CONFIDENCE

    def test_relationship_source_is_resolved_to_the_constructed_entitys_ref(self, sql_prompt) -> None:
        raw = {
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
        result = parse_technical_response(
            raw, prompt=sql_prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert not result.failures
        [candidate] = result.relationships
        assert candidate.source_ref == EntityRef(type=EntityType.PIPELINE, id="stg_customers")
        assert candidate.target_kind is EntityType.DATA_ASSET
        assert candidate.target_symbolic_name == "raw_customers"
        assert candidate.target_ref is None  # not yet resolved -- discovery.resolve's job


class TestTechnicalResponseRejection:
    def test_schema_violation_rejects_the_whole_response(self, sql_prompt) -> None:
        raw = {"entities": [{"entity_type": "Pipeline", "local_id": "p1"}], "relationships": []}
        result = parse_technical_response(
            raw, prompt=sql_prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert result.entities == []
        assert result.relationships == []
        assert len(result.failures) == 1
        assert result.failures[0].kind == "schema_violation"

    def test_duplicate_suggested_id_fails_only_that_item(self, sql_prompt) -> None:
        prompt = build_technical_prompt(
            relative_path=Path("f"), content="x", source_kind="sql"
        )
        raw = {
            "entities": [
                {
                    "entity_type": "Pipeline",
                    "local_id": "p1",
                    "suggested_id": "dup",
                    "pipeline_kind": "dbt_model",
                    "confidence": 0.9,
                },
                {
                    "entity_type": "Pipeline",
                    "local_id": "p2",
                    "suggested_id": "dup",
                    "pipeline_kind": "dbt_model",
                    "confidence": 0.9,
                },
            ],
            "relationships": [],
        }
        result = parse_technical_response(
            raw, prompt=prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert len(result.entities) == 1
        assert any(f.kind == "duplicate_suggested_id" for f in result.failures)

    def test_relationship_with_unknown_source_local_id_is_recorded_not_dropped_silently(
        self, sql_prompt
    ) -> None:
        raw = {
            "entities": [
                {
                    "entity_type": "Pipeline",
                    "local_id": "p1",
                    "suggested_id": "x",
                    "pipeline_kind": "dbt_model",
                    "confidence": 0.9,
                }
            ],
            "relationships": [
                {
                    "type": "DEPENDS_ON",
                    "source_local_id": "does-not-exist",
                    "target_kind": "DataAsset",
                    "target_symbolic_name": "y",
                    "confidence": 0.8,
                }
            ],
        }
        result = parse_technical_response(
            raw, prompt=sql_prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert result.relationships == []
        assert any(f.kind == "unknown_relationship_source" for f in result.failures)


class TestSchemaDefinitionAssetRefResolution:
    def test_asset_ref_resolves_against_an_earlier_entity_in_the_same_response(self) -> None:
        prompt = build_technical_prompt(
            relative_path=Path("seeds/x.csv"), content="a,b\n1,2", source_kind="csv"
        )
        raw = {
            "entities": [
                {
                    "entity_type": "DataAsset",
                    "local_id": "a1",
                    "suggested_id": "x",
                    "asset_kind": "dataset",
                    "confidence": 0.85,
                },
                {
                    "entity_type": "SchemaDefinition",
                    "local_id": "s1",
                    "suggested_id": "x.schema",
                    "asset_ref_local_id": "a1",
                    "fields": [{"name": "a", "data_type": "string"}],
                    "confidence": 0.8,
                },
            ],
            "relationships": [],
        }
        result = parse_technical_response(
            raw, prompt=prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert not result.failures
        schema_def = next(e for e in result.entities if e.entity_type is EntityType.SCHEMA_DEFINITION)
        assert schema_def.asset_ref == EntityRef(type=EntityType.DATA_ASSET, id="x")

    def test_unresolvable_asset_ref_local_id_fails_only_that_entity(self) -> None:
        prompt = build_technical_prompt(
            relative_path=Path("seeds/x.csv"), content="a,b\n1,2", source_kind="csv"
        )
        raw = {
            "entities": [
                {
                    "entity_type": "SchemaDefinition",
                    "local_id": "s1",
                    "suggested_id": "x.schema",
                    "asset_ref_local_id": "does-not-exist",
                    "fields": [],
                    "confidence": 0.8,
                }
            ],
            "relationships": [],
        }
        result = parse_technical_response(
            raw, prompt=prompt, source_document="f", project_ref=PROJECT_REF
        )
        assert result.entities == []
        assert any(f.kind == "entity_construction_failed" for f in result.failures)


class TestDeliveryResponse:
    @pytest.fixture
    def known(self):
        return {"p1": EntityRef(type=EntityType.PIPELINE, id="p1")}

    @pytest.fixture
    def delivery_prompt(self, known):
        entries = [
            KnownEntity(ref=ref, entity_type=ref.type, name=ref.id, path=None)
            for ref in known.values()
        ]
        return build_delivery_prompt(relative_path=Path("README.md"), content="mentions p1", known_entities=entries)

    def test_valid_describes_response(self, known, delivery_prompt) -> None:
        raw = {
            "entities": [
                {
                    "entity_type": "DeliveryArtifact",
                    "local_id": "doc",
                    "suggested_id": "readme",
                    "artifact_key": "readme",
                    "artifact_kind": "project-readme",
                    "confidence": 0.85,
                }
            ],
            "relationships": [
                {"type": "DESCRIBES", "source_local_id": "doc", "target_id": "p1", "confidence": 0.75}
            ],
        }
        result = parse_delivery_response(
            raw, prompt=delivery_prompt, source_document="README.md", project_ref=PROJECT_REF, known_entities=known
        )
        assert not result.failures
        [artifact] = result.entities
        assert artifact.project_ref == PROJECT_REF
        [candidate] = result.relationships
        assert candidate.target_ref == known["p1"]
        assert candidate.target_kind is None  # already resolved, not a symbolic candidate

    def test_target_id_not_in_known_entities_is_rejected_even_if_it_somehow_reached_here(
        self, known, delivery_prompt
    ) -> None:
        """Belt-and-suspenders: the schema already constrains target_id to
        an enum, but parse_delivery_response must never trust a client to
        have actually enforced the schema it was given."""
        raw = {
            "entities": [
                {
                    "entity_type": "DeliveryArtifact",
                    "local_id": "doc",
                    "suggested_id": "readme",
                    "artifact_key": "readme",
                    "artifact_kind": "project-readme",
                    "confidence": 0.85,
                }
            ],
            "relationships": [
                {"type": "DESCRIBES", "source_local_id": "doc", "target_id": "p1", "confidence": 0.75}
            ],
        }
        result = parse_delivery_response(
            raw,
            prompt=delivery_prompt,
            source_document="README.md",
            project_ref=PROJECT_REF,
            known_entities={},  # simulate a caller passing a mismatched index
        )
        assert result.relationships == []
        assert any(f.kind == "unknown_describes_target" for f in result.failures)
