"""JSON Schema artifacts: coverage, drift and shape.

The files under ``schemas/`` are published contracts that consumers outside this
repository validate against, so they are committed. That only works if they
cannot silently fall behind the models.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.enums import EntityType
from domain.metamodel.version import METAMODEL_VERSION
from scripts.export_schemas import SCHEMA_DIR, build_schemas, check_schemas


class TestDrift:
    def test_committed_schemas_match_the_models(self) -> None:
        problems = check_schemas()
        assert not problems, "run: python scripts/export_schemas.py\n" + "\n".join(problems)


class TestCoverage:
    def test_every_entity_type_has_a_schema(self) -> None:
        schemas = build_schemas()
        for entity_type in EntityType:
            assert entity_type.value in schemas, f"no schema for {entity_type.value}"

    def test_every_entity_type_has_an_implementation(self) -> None:
        assert set(ENTITY_CLASSES) == set(EntityType)

    def test_relationship_contract_is_published(self) -> None:
        schemas = build_schemas()
        assert "Relationship" in schemas and "RelationshipTypeSpec" in schemas

    def test_index_groups_entities_by_twin(self) -> None:
        """A consumer must be able to find the delivery contract on its own."""
        index = build_schemas()["index"]
        by_twin = index["entities_by_twin"]
        assert set(by_twin) == {"TECHNICAL", "DELIVERY", "SHARED"}
        assert "DeliveryTask" in by_twin["DELIVERY"]
        assert "Pipeline" in by_twin["TECHNICAL"]


class TestShape:
    @pytest.mark.parametrize("name", sorted(build_schemas()))
    def test_each_document_declares_dialect_and_id(self, name: str) -> None:
        schema = build_schemas()[name]
        assert schema["$schema"].startswith("https://json-schema.org/draft/")
        assert schema["$id"].endswith(".json")

    def test_entity_schemas_are_stamped_with_the_metamodel_version(self) -> None:
        for name, schema in build_schemas().items():
            if name == "index":
                continue
            assert schema["x-metamodel-version"] == METAMODEL_VERSION

    def test_entity_schemas_declare_their_twin(self) -> None:
        for entity_type in EntityType:
            schema = build_schemas()[entity_type.value]
            assert schema["x-twin"] in {"TECHNICAL", "DELIVERY", "SHARED"}

    @pytest.mark.parametrize(
        "entity_type",
        [
            EntityType.PROJECT,
            EntityType.PIPELINE,
            EntityType.DATA_ASSET,
            EntityType.EVIDENCE,
            EntityType.DELIVERY_TASK,
            EntityType.APPROVAL_GATE,
        ],
    )
    def test_provenance_is_required_on_discovered_entities(self, entity_type) -> None:
        """Discovery cannot emit a fact -- technical or delivery -- unattributed."""
        schema = build_schemas()[entity_type.value]
        assert "provenance" in schema.get("required", [])

    def test_committed_files_are_valid_json(self) -> None:
        for path in sorted(Path(SCHEMA_DIR).glob("*.schema.json")):
            json.loads(path.read_text(encoding="utf-8"))
