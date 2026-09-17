"""The extraction contract: what one ``ExtractionClient.extract()`` call
gets asked for, and the JSON Schema its response must conform to.

Every entity type's extraction schema is derived live from the Pydantic
model -- the same ``model_json_schema(mode="serialization")`` call
``scripts/export_schemas.py`` uses -- filtered down to the fields an agent
should actually populate. The committed files under ``schemas/`` are
published validation targets for external consumers (per that script's own
docstring), not tuned as an LLM generation target, and re-deriving live here
avoids a second, driftable copy of the same information.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.metamodel.base import EntityRef
from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.enums import EntityType
from discovery.walk import CI_WORKFLOW, COMPOSE, CSV, DOCKERFILE, SQL, TERRAFORM, YAML_CONFIG

#: Base-class fields every ``ProvenancedEntity`` carries. Never model-
#: generated -- the platform assigns identity, versioning, and provenance
#: bookkeeping itself (`discovery.extraction.parse_response` fills these
#: in). Listed once, mechanically subtracted, rather than hand-maintained
#: per entity type.
_BASE_FIELD_NAMES = frozenset(
    {
        "id",
        "name",
        "description",
        "entity_type",
        "twin",
        "labels",
        "attributes",
        "version",
        "metamodel_version",
        "created_at",
        "updated_at",
        "provenance",
        "confidence",
        "evidence_refs",
        "discovered_by",
        "discovered_at",
        "valid_from",
        "valid_until",
        "human_verified_by",
        "human_verified_at",
        "source_document",
        "source_section",
        "extraction_method",
    }
)

#: Which entity type schemas are relevant to a given technical source kind.
#: A source kind mapped to an empty tuple has no legal target in the
#: metamodel today (dbt's own YAML config, currently) -- the orchestrator
#: records a skip for it rather than forcing output with nowhere honest to
#: land. Extending to a new source kind is one entry here, not a new parser.
SOURCE_KIND_ENTITY_TYPES: dict[str, tuple[EntityType, ...]] = {
    SQL: (EntityType.PIPELINE, EntityType.DATA_ASSET),
    CSV: (EntityType.DATA_ASSET, EntityType.SCHEMA_DEFINITION),
    DOCKERFILE: (EntityType.INFRASTRUCTURE,),
    COMPOSE: (EntityType.INFRASTRUCTURE,),
    CI_WORKFLOW: (EntityType.PIPELINE,),
    TERRAFORM: (EntityType.INFRASTRUCTURE,),
    YAML_CONFIG: (),
}

#: `.sql` files under a dbt-shaped project never produce a `CodeArtifact` --
#: `Pipeline.source_path` already captures the location, and the registry
#: has no relationship type that lets `Pipeline` be the *source* of a
#: `CONTAINS` edge, so a separately-extracted `CodeArtifact` would be an
#: orphaned node with no legal edge back to its own `Pipeline`. Enforced
#: structurally by `SOURCE_KIND_ENTITY_TYPES` simply never offering it.
assert EntityType.CODE_ARTIFACT not in SOURCE_KIND_ENTITY_TYPES.get(SQL, ())

#: `DESCRIBES`' legal target types (`metamodel-registry/relationship_types.yaml`,
#: the `DESCRIBES` entry) -- what a Markdown extraction pass is allowed to
#: point at. `Repository` and `Project` are deliberately absent.
DESCRIBES_LEGAL_TARGET_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.PIPELINE,
        EntityType.DATA_ASSET,
        EntityType.ARCHITECTURE_ELEMENT,
        EntityType.INFRASTRUCTURE,
        EntityType.CODE_ARTIFACT,
    }
)

#: Model self-reported confidence is clamped into this range before it ever
#: reaches a `Provenanced` model -- see `parse_response.py`. Named here too
#: so the prompt can tell the model the range it should reason within.
#: Explicitly an initial estimate, not a calibrated constant.
MIN_CONFIDENCE = 0.05
MAX_CONFIDENCE = 0.90

#: A file larger than this is truncated before being sent, with the
#: truncation flagged in the prompt text (not silently dropped past this
#: point) -- bounds prompt size against a pathological input file.
MAX_CONTENT_CHARS = 20_000


def content_schema_for(entity_type: EntityType) -> dict[str, Any]:
    """The content-field-only schema for one entity type: what an agent
    should populate, once bookkeeping fields and every ``EntityRef``-shaped
    field are subtracted, and a required ``confidence`` is added.

    ``EntityRef`` fields (``project_ref``, ``asset_ref``, ``input_refs``,
    ``describes_refs`` and every field like them) are stripped uniformly,
    not just the base-class ones: they are denormalized mirrors of what the
    relationship graph already captures authoritatively (the same reasoning
    ``Pipeline.input_refs``/``output_refs`` already document -- "the graph
    projection turns these into first-class relationships"), and asking an
    agent to correctly produce a nested, typed reference object from inside
    one file's local context is a reliability risk with no upside: the
    facts they'd carry are already expressed as relationship candidates.
    ``project_ref`` is platform-injected after construction instead (every
    entity a run produces belongs to the one project being discovered --
    that is deterministic context, not something to ask an agent to
    parrot back). ``SchemaDefinition.asset_ref`` is the one field genuinely
    needed from within a single response (a seed file's schema belongs to
    that same file's data asset) and gets a narrow, explicit exception --
    see ``_tagged_schema_for``.

    Does not include ``entity_type`` itself -- that is added as a
    discriminator by ``_tagged_schema_for`` when several entity types share
    one response.
    """
    model = ENTITY_CLASSES[entity_type]
    full = model.model_json_schema(mode="serialization")
    properties = {
        key: value
        for key, value in full.get("properties", {}).items()
        if key not in _BASE_FIELD_NAMES and "EntityRef" not in json.dumps(value)
    }
    properties["confidence"] = {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "How certain this reading is, not whether the fact exists at all.",
    }
    stripped_names = {
        key
        for key, value in full.get("properties", {}).items()
        if key not in _BASE_FIELD_NAMES and "EntityRef" in json.dumps(value)
    }
    required = sorted(
        {
            name
            for name in full.get("required", [])
            if name not in _BASE_FIELD_NAMES and name not in stripped_names
        }
        | {"confidence"}
    )
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    if "$defs" in full:
        schema["$defs"] = full["$defs"]
    return schema


#: A conservative, deterministic-to-slugify identifier shape. The platform
#: derives the real `id`/`name` from `suggested_id` (never trusts an
#: arbitrary agent-chosen string as identity outright) -- resolved in
#: `discovery.extraction.parse_response`.
_SUGGESTED_ID_PATTERN = r"^[a-zA-Z0-9_.-]{1,200}$"

#: `SchemaDefinition.asset_ref` is the one `EntityRef` field genuinely
#: needed from inside a single response: a seed file's schema belongs to
#: that same file's data asset, known only by its `local_id` within this
#: response, not as a resolvable id yet. Named explicitly rather than
#: generalizing the exception mechanism beyond this one real case.
_ASSET_REF_LOCAL_ID_FIELD = "asset_ref_local_id"


def _tagged_schema_for(entity_type: EntityType) -> dict[str, Any]:
    """`content_schema_for` plus a required `entity_type`/`local_id`/
    `suggested_id` discriminator, for use as one variant of a multi-type
    `entities` array.
    """
    schema = content_schema_for(entity_type)
    properties = dict(schema["properties"])
    properties["entity_type"] = {"const": entity_type.value}
    properties["local_id"] = {
        "type": "string",
        "description": "A short id unique within this response, referenced by "
        "relationship candidates in the same response as their source.",
    }
    properties["suggested_id"] = {
        "type": "string",
        "pattern": _SUGGESTED_ID_PATTERN,
        "description": "A short, stable, human-meaningful identifier for this entity "
        "(e.g. the dbt model name, the compose service name). Lowercase where natural, "
        "alphanumeric plus underscore/hyphen/period only.",
    }
    required = [*schema["required"], "entity_type", "local_id", "suggested_id"]

    if entity_type is EntityType.SCHEMA_DEFINITION:
        properties[_ASSET_REF_LOCAL_ID_FIELD] = {
            "type": "string",
            "description": "The local_id, from THIS SAME response, of the DataAsset this "
            "schema describes. List that DataAsset earlier in your entities array than "
            "this SchemaDefinition.",
        }
        required.append(_ASSET_REF_LOCAL_ID_FIELD)

    schema = {**schema, "properties": properties, "required": required}
    return schema


_RELATIONSHIP_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "description": "Relationship type key, e.g. DEPENDS_ON."},
        "source_local_id": {
            "type": "string",
            "description": "The local_id of the entity (from this response) that is the source.",
        },
        "target_kind": {
            "enum": [t.value for t in EntityType],
            "description": "Entity type the target is expected to be, e.g. Pipeline or DataAsset.",
        },
        "target_symbolic_name": {
            "type": "string",
            "description": "The name/identifier the target was referred to by in the source text "
            "(e.g. the argument to a ref() call) -- not a resolved id.",
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["type", "source_local_id", "target_kind", "target_symbolic_name", "confidence"],
    "additionalProperties": False,
}


def _describes_candidate_schema(known_entity_ids: list[str]) -> dict[str, Any]:
    """`target_id` is constrained to exactly the ids offered in the prompt --
    an invalid target is a schema violation, not a separate semantic check.
    An empty `known_entity_ids` makes every candidate schema-invalid, which
    is correct: there is nothing legal to describe yet.
    """
    return {
        "type": "object",
        "properties": {
            "type": {"const": "DESCRIBES"},
            "source_local_id": {
                "type": "string",
                "description": "The local_id of the DeliveryArtifact (from this response) "
                "that describes the target.",
            },
            "target_id": {
                "enum": known_entity_ids,
                "description": "The id of a technical entity from the supplied known-entities "
                "index. Must be one of the ids you were given -- never invent one.",
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["type", "source_local_id", "target_id", "confidence"],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class ExtractionPrompt:
    """Everything one `ExtractionClient.extract()` call needs."""

    prompt: str
    response_schema: dict[str, Any]


@dataclass(frozen=True)
class KnownEntity:
    """One already-discovered technical entity, offered to a delivery-file
    extraction pass as a candidate `DESCRIBES` target."""

    ref: EntityRef
    entity_type: EntityType
    name: str
    path: str | None


def _truncate(content: str) -> tuple[str, bool]:
    if len(content) <= MAX_CONTENT_CHARS:
        return content, False
    return content[:MAX_CONTENT_CHARS], True


def _hoist_defs(variants: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Strip each variant's own top-level `$defs` and merge them into one dict.

    A `$ref` like `#/$defs/EntityRef` resolves against the *document root*,
    not the subschema it lexically appears in -- so a `$defs` block left
    sitting on an individual `oneOf` variant is unreachable from inside it.
    Every variant's `$defs` must be hoisted to the response schema's own
    root instead. Colliding keys (e.g. two entity types both defining
    `EntityRef`) are assumed structurally identical, since they come from
    the same shared base types -- not deep-merged, just overwritten.
    """
    merged: dict[str, Any] = {}
    stripped: list[dict[str, Any]] = []
    for variant in variants:
        variant = dict(variant)
        merged.update(variant.pop("$defs", {}))
        stripped.append(variant)
    return stripped, merged


def _response_schema_for_entity_types(entity_types: tuple[EntityType, ...]) -> dict[str, Any]:
    variants, defs = _hoist_defs([_tagged_schema_for(entity_type) for entity_type in entity_types])
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entities": {"type": "array", "items": {"oneOf": variants}},
            "relationships": {"type": "array", "items": _RELATIONSHIP_CANDIDATE_SCHEMA},
        },
        "required": ["entities", "relationships"],
        "additionalProperties": False,
    }
    if defs:
        schema["$defs"] = defs
    return schema


def build_technical_prompt(
    *, relative_path: Path, content: str, source_kind: str
) -> ExtractionPrompt:
    """Build the prompt and response schema for one technical candidate file.

    Sibling file content is never included here -- only this one file's
    text -- which is what bounds prompt size and keeps per-file extraction
    independently replayable.
    """
    entity_types = SOURCE_KIND_ENTITY_TYPES.get(source_kind, ())
    if not entity_types:
        raise ValueError(
            f"source_kind {source_kind!r} has no target entity types; the caller should "
            "have skipped this file rather than building a prompt for it"
        )

    truncated, was_truncated = _truncate(content)
    truncation_note = (
        f"\n\n[content truncated at {MAX_CONTENT_CHARS} characters]" if was_truncated else ""
    )

    prompt = (
        f"You are extracting structured facts from one file in a data engineering "
        f"project, for a metamodel that tracks provenance explicitly. Everything you "
        f"report is treated as INFERRED, never as certain -- your job is to read "
        f"accurately and report an honest confidence per fact, in the range "
        f"[{MIN_CONFIDENCE}, {MAX_CONFIDENCE}].\n\n"
        f"File: {relative_path.as_posix()}\n"
        f"Source kind: {source_kind}\n\n"
        f"Extract entities of these types only: {', '.join(t.value for t in entity_types)}. "
        f"For each entity, assign a short `local_id` unique within your response. "
        f"Extract relationship candidates naming the *symbolic* name a target was referred "
        f"to by in the text (e.g. a ref() argument, a depends_on: service name) -- never "
        f"invent a resolved id; the platform resolves symbolic names separately.\n\n"
        f"--- file content ---\n{truncated}{truncation_note}\n--- end file content ---"
    )
    return ExtractionPrompt(
        prompt=prompt, response_schema=_response_schema_for_entity_types(entity_types)
    )


def build_delivery_prompt(
    *, relative_path: Path, content: str, known_entities: list[KnownEntity]
) -> ExtractionPrompt:
    """Build the prompt and response schema for one delivery (Markdown) file.

    `known_entities` is filtered by the caller to `DESCRIBES`-legal target
    types before reaching here (`Repository`/`Project` excluded). The model
    echoes an id directly from this index rather than a name for later
    matching -- "does this document actually describe that pipeline" is a
    genuinely semantic judgment, made once, with the full prose in view.
    """
    truncated, was_truncated = _truncate(content)
    truncation_note = (
        f"\n\n[content truncated at {MAX_CONTENT_CHARS} characters]" if was_truncated else ""
    )
    index_lines = [
        f"- id={entry.ref.id!r} type={entry.entity_type.value} name={entry.name!r}"
        + (f" path={entry.path!r}" if entry.path else "")
        for entry in known_entities
    ]
    index_text = "\n".join(index_lines) if index_lines else "(none discovered yet)"

    prompt = (
        f"You are extracting a delivery-document fact from one Markdown file, for a "
        f"metamodel that tracks provenance explicitly. Report an honest confidence per "
        f"fact, in the range [{MIN_CONFIDENCE}, {MAX_CONFIDENCE}].\n\n"
        f"File: {relative_path.as_posix()}\n\n"
        f"Extract exactly one DeliveryArtifact entity describing this document (assign it "
        f"local_id 'doc'). Then, for every technical entity below that this document "
        f"genuinely describes, emit a DESCRIBES relationship candidate whose target_id is "
        f"EXACTLY one of the ids listed -- never invent an id, never target anything not "
        f"in this list:\n{index_text}\n\n"
        f"--- file content ---\n{truncated}{truncation_note}\n--- end file content ---"
    )
    [artifact_item], defs = _hoist_defs([_tagged_schema_for(EntityType.DELIVERY_ARTIFACT)])
    known_ids = [entry.ref.id for entry in known_entities]
    response_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "entities": {"type": "array", "items": artifact_item},
            "relationships": {
                "type": "array",
                "items": _describes_candidate_schema(known_ids),
            },
        },
        "required": ["entities", "relationships"],
        "additionalProperties": False,
    }
    if defs:
        response_schema["$defs"] = defs
    return ExtractionPrompt(prompt=prompt, response_schema=response_schema)


def response_schema_json(prompt: ExtractionPrompt) -> str:
    """Convenience: the response schema as a compact JSON string, for
    clients that need to embed it as text rather than pass it structurally."""
    return json.dumps(prompt.response_schema, sort_keys=True)
