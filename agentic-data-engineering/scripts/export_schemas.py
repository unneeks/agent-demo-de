#!/usr/bin/env python3
"""Export JSON Schema for every metamodel entity, and detect drift.

The committed files under ``schemas/`` are published artifacts: they are what a
non-Python discovery adapter or an external marketplace contributor validates
against. Generating them on the fly would mean nobody outside this repository
could rely on them, so they are committed -- and ``--check`` fails the build if
the committed copies no longer match the models.

Usage:
    python scripts/export_schemas.py            # write schemas/
    python scripts/export_schemas.py --check    # fail on drift, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.entities import ENTITY_CLASSES, VALUE_OBJECTS  # noqa: E402
from domain.metamodel.relationships import Relationship, RelationshipTypeSpec  # noqa: E402
from domain.metamodel.version import METAMODEL_VERSION  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _schema_for(name: str, model: Any, twin: str | None = None) -> dict[str, Any]:
    schema = model.model_json_schema(mode="serialization")
    document = {
        "$schema": SCHEMA_DIALECT,
        "$id": f"https://agentic-data-engineering/schemas/{name}.schema.json",
        "x-metamodel-version": METAMODEL_VERSION,
    }
    if twin:
        document["x-twin"] = twin
    document.update(schema)
    return document


@lru_cache(maxsize=1)
def build_schemas() -> dict[str, dict[str, Any]]:
    """Every schema document, keyed by output filename stem.

    Cached: generation is pure and deterministic, and both the writer and the
    drift checker call it repeatedly.
    """
    schemas: dict[str, dict[str, Any]] = {}

    for entity_type, model in ENTITY_CLASSES.items():
        twin = model.model_fields["twin"].default
        schemas[entity_type.value] = _schema_for(
            entity_type.value, model, twin=twin.value if twin else None
        )

    for name, model in VALUE_OBJECTS.items():
        schemas[name] = _schema_for(name, model)

    # Relationships are not entities but are just as much part of the contract.
    schemas["Relationship"] = _schema_for("Relationship", Relationship)
    schemas["RelationshipTypeSpec"] = _schema_for("RelationshipTypeSpec", RelationshipTypeSpec)

    # An index, so a consumer can discover the set without listing a directory.
    by_twin: dict[str, list[str]] = {}
    for entity_type, model in ENTITY_CLASSES.items():
        twin = model.model_fields["twin"].default
        by_twin.setdefault(twin.value if twin else "SHARED", []).append(entity_type.value)

    schemas["index"] = {
        "$schema": SCHEMA_DIALECT,
        "$id": "https://agentic-data-engineering/schemas/index.json",
        "metamodel_version": METAMODEL_VERSION,
        "entities": sorted(e.value for e in ENTITY_CLASSES),
        "entities_by_twin": {k: sorted(v) for k, v in sorted(by_twin.items())},
        "value_objects": sorted(VALUE_OBJECTS),
        "additional": ["Relationship", "RelationshipTypeSpec"],
    }
    return schemas


def _serialize(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_schemas(target: Path = SCHEMA_DIR) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    schemas = build_schemas()
    written = []
    for name, schema in schemas.items():
        path = target / f"{name}.schema.json"
        path.write_text(_serialize(schema), encoding="utf-8")
        written.append(path)

    # Remove schemas for entities that no longer exist, so a deleted entity does
    # not leave a stale contract behind for someone to keep validating against.
    expected = {f"{name}.schema.json" for name in schemas}
    for existing in target.glob("*.schema.json"):
        if existing.name not in expected:
            existing.unlink()
    return written


def check_schemas(target: Path = SCHEMA_DIR) -> list[str]:
    """Return drift descriptions. Empty means the artifacts are current."""
    problems: list[str] = []
    schemas = build_schemas()

    for name, schema in schemas.items():
        path = target / f"{name}.schema.json"
        if not path.is_file():
            problems.append(f"missing: {path.relative_to(REPO_ROOT)}")
        elif path.read_text(encoding="utf-8") != _serialize(schema):
            problems.append(f"out of date: {path.relative_to(REPO_ROOT)}")

    expected = {f"{name}.schema.json" for name in schemas}
    for existing in sorted(target.glob("*.schema.json")):
        if existing.name not in expected:
            problems.append(f"orphaned: {existing.relative_to(REPO_ROOT)}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed schemas differ from the models. Writes nothing.",
    )
    args = parser.parse_args()

    if args.check:
        problems = check_schemas()
        if problems:
            print("JSON Schema artifacts are out of date:", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            print("\nRun: python scripts/export_schemas.py", file=sys.stderr)
            return 1
        print(f"schemas up to date ({len(build_schemas())} documents)")
        return 0

    written = write_schemas()
    print(f"wrote {len(written)} schema documents to {SCHEMA_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
