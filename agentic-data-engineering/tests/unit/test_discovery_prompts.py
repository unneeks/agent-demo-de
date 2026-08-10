"""The extraction contract: schema derivation and prompt building.

Grounded in real JSON Schema validation (`jsonschema`), not just shape
assertions -- a schema that jsonschema itself rejects as malformed would
never actually constrain a real extraction call.
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from domain.metamodel.enums import EntityType
from discovery.extraction.prompts import (
    DESCRIBES_LEGAL_TARGET_TYPES,
    SOURCE_KIND_ENTITY_TYPES,
    KnownEntity,
    build_delivery_prompt,
    build_technical_prompt,
    content_schema_for,
)
from domain.metamodel.base import EntityRef


class TestContentSchemaFor:
    def test_bookkeeping_fields_are_excluded(self) -> None:
        schema = content_schema_for(EntityType.PIPELINE)
        for field in ("id", "name", "entity_type", "provenance", "discovered_by", "twin"):
            assert field not in schema["properties"]

    def test_entity_ref_shaped_fields_are_excluded(self) -> None:
        """`project_ref` (single ref) and `input_refs`/`output_refs` (ref
        lists) are all EntityRef-shaped -- stripped uniformly, not just the
        base-class fields."""
        schema = content_schema_for(EntityType.PIPELINE)
        for field in ("project_ref", "input_refs", "output_refs", "code_ref"):
            assert field not in schema["properties"]

    def test_confidence_is_required(self) -> None:
        schema = content_schema_for(EntityType.PIPELINE)
        assert schema["properties"]["confidence"]["type"] == "number"
        assert "confidence" in schema["required"]

    def test_content_fields_remain(self) -> None:
        schema = content_schema_for(EntityType.PIPELINE)
        assert "pipeline_kind" in schema["properties"]
        assert "pipeline_kind" in schema["required"]  # required on the real Pydantic model


class TestBuildTechnicalPrompt:
    def test_produces_a_valid_json_schema(self) -> None:
        prompt = build_technical_prompt(
            relative_path=Path("models/a.sql"), content="select 1", source_kind="sql"
        )
        jsonschema.Draft202012Validator.check_schema(prompt.response_schema)

    def test_file_line_is_present_for_replay_lookup(self) -> None:
        prompt = build_technical_prompt(
            relative_path=Path("models/a.sql"), content="select 1", source_kind="sql"
        )
        assert "File: models/a.sql\n" in prompt.prompt

    def test_a_valid_response_validates(self) -> None:
        prompt = build_technical_prompt(
            relative_path=Path("seeds/x.csv"), content="a,b\n1,2", source_kind="csv"
        )
        sample = {
            "entities": [
                {
                    "entity_type": "DataAsset",
                    "local_id": "a1",
                    "suggested_id": "x",
                    "asset_kind": "dataset",
                    "confidence": 0.8,
                }
            ],
            "relationships": [],
        }
        jsonschema.validate(sample, prompt.response_schema)

    def test_unmapped_source_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="no target entity types"):
            build_technical_prompt(
                relative_path=Path("dbt_project.yml"), content="x", source_kind="yaml_config"
            )

    def test_every_technical_source_kind_produces_a_valid_schema(self) -> None:
        for source_kind, entity_types in SOURCE_KIND_ENTITY_TYPES.items():
            if not entity_types:
                continue
            prompt = build_technical_prompt(
                relative_path=Path("f"), content="content", source_kind=source_kind
            )
            jsonschema.Draft202012Validator.check_schema(prompt.response_schema)

    def test_content_is_truncated_past_the_cap(self) -> None:
        from discovery.extraction.prompts import MAX_CONTENT_CHARS

        huge = "x" * (MAX_CONTENT_CHARS + 500)
        prompt = build_technical_prompt(
            relative_path=Path("a.sql"), content=huge, source_kind="sql"
        )
        assert "[content truncated" in prompt.prompt
        assert len(prompt.prompt) < len(huge) + 2000


class TestSchemaDefinitionSpecialCase:
    def test_csv_offers_asset_ref_local_id_not_asset_ref(self) -> None:
        schema = content_schema_for(EntityType.SCHEMA_DEFINITION)
        assert "asset_ref" not in schema["properties"]
        prompt = build_technical_prompt(
            relative_path=Path("seeds/x.csv"), content="a,b\n1,2", source_kind="csv"
        )
        variants = prompt.response_schema["properties"]["entities"]["items"]["oneOf"]
        schema_def_variant = next(
            v for v in variants if v["properties"]["entity_type"]["const"] == "SchemaDefinition"
        )
        assert "asset_ref_local_id" in schema_def_variant["required"]


class TestBuildDeliveryPrompt:
    def test_produces_a_valid_json_schema(self) -> None:
        known = [
            KnownEntity(
                ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
                entity_type=EntityType.PIPELINE,
                name="p1",
                path="models/p1.sql",
            )
        ]
        prompt = build_delivery_prompt(
            relative_path=Path("README.md"), content="mentions p1", known_entities=known
        )
        jsonschema.Draft202012Validator.check_schema(prompt.response_schema)

    def test_target_id_is_constrained_to_known_ids(self) -> None:
        known = [
            KnownEntity(
                ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
                entity_type=EntityType.PIPELINE,
                name="p1",
                path=None,
            )
        ]
        prompt = build_delivery_prompt(
            relative_path=Path("README.md"), content="mentions p1", known_entities=known
        )
        target_schema = prompt.response_schema["properties"]["relationships"]["items"]["properties"][
            "target_id"
        ]
        assert target_schema["enum"] == ["p1"]

    def test_an_out_of_index_target_id_fails_validation(self) -> None:
        known = [
            KnownEntity(
                ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
                entity_type=EntityType.PIPELINE,
                name="p1",
                path=None,
            )
        ]
        prompt = build_delivery_prompt(
            relative_path=Path("README.md"), content="x", known_entities=known
        )
        bad = {
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
                {"type": "DESCRIBES", "source_local_id": "doc", "target_id": "invented", "confidence": 0.7}
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, prompt.response_schema)

    def test_empty_known_entities_still_produces_a_valid_schema(self) -> None:
        prompt = build_delivery_prompt(relative_path=Path("README.md"), content="x", known_entities=[])
        jsonschema.Draft202012Validator.check_schema(prompt.response_schema)


class TestDescribesLegalTargetTypes:
    def test_repository_and_project_are_not_legal_targets(self) -> None:
        assert EntityType.REPOSITORY not in DESCRIBES_LEGAL_TARGET_TYPES
        assert EntityType.PROJECT not in DESCRIBES_LEGAL_TARGET_TYPES

    def test_pipeline_and_data_asset_are_legal_targets(self) -> None:
        assert EntityType.PIPELINE in DESCRIBES_LEGAL_TARGET_TYPES
        assert EntityType.DATA_ASSET in DESCRIBES_LEGAL_TARGET_TYPES
