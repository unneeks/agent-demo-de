"""Turns a raw `ExtractionClient` response into validated entities and
relationship candidates -- the most important validation boundary in this
phase.

Two layers of defense, deliberately not just one: (1) `jsonschema.validate`
against the exact schema the client was asked to conform to, which also
enforces the ``DESCRIBES`` ``target_id`` enum -- so a hallucinated id is
already a schema violation, not something a second lookup has to catch; (2)
Pydantic construction of the real entity, which enforces every metamodel
invariant (`extra="forbid"`, provenance validators, entity-specific field
constraints) regardless of what the JSON Schema pass already caught. Nothing
here is a partial write: a response that fails schema validation is
rejected wholesale; within a conforming response, a single malformed item
(a duplicate `suggested_id`, a relationship source that doesn't resolve)
fails only that item, recorded, never silently dropped and never guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import jsonschema
from pydantic import ValidationError

from domain.metamodel.base import EntityRef, MetamodelEntity
from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.enums import EntityType, ExtractionMethod, ProvenanceState
from discovery.extraction.prompts import (
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    _ASSET_REF_LOCAL_ID_FIELD,
    ExtractionPrompt,
)
from discovery.result import DiscoveryFailure

#: One uniform discoverer string for every source kind, deliberately not
#: suffixed per source (`source_document` already carries that specificity;
#: suffixing this string would quietly reintroduce the special-casing the
#: uniform-extraction design rejects, just relocated into a literal).
DISCOVERED_BY = "agent-extraction@0.1.0"

_NON_CONTENT_KEYS = frozenset({"entity_type", "local_id", "suggested_id", "confidence"})


@dataclass(frozen=True)
class RelationshipCandidate:
    """One relationship the agent proposed.

    ``source_ref`` is always resolved immediately -- the source is always an
    entity from this same response. For a technical candidate, the target is
    named symbolically (``target_kind``/``target_symbolic_name``) and
    resolved later, across every file's output, by `discovery.resolve`. For
    a delivery candidate, the target is already a real ref: the schema
    constrained ``target_id`` to a known-entities index before the response
    was even produced.
    """

    type: str
    source_ref: EntityRef
    confidence: float
    target_kind: EntityType | None = None
    target_symbolic_name: str | None = None
    target_ref: EntityRef | None = None


@dataclass(frozen=True)
class ParsedResponse:
    entities: list[MetamodelEntity] = field(default_factory=list)
    relationships: list[RelationshipCandidate] = field(default_factory=list)
    failures: list[DiscoveryFailure] = field(default_factory=list)


def _clamp_confidence(raw: Any) -> float:
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, float(raw)))


def _construct_entity(
    item: dict[str, Any],
    *,
    source_document: str,
    project_ref: EntityRef,
    local_id_to_ref: dict[str, EntityRef],
) -> MetamodelEntity:
    entity_type = EntityType(item["entity_type"])
    model = ENTITY_CLASSES[entity_type]
    identity = item["suggested_id"]

    content = {key: value for key, value in item.items() if key not in _NON_CONTENT_KEYS}

    if entity_type is EntityType.SCHEMA_DEFINITION:
        asset_local_id = content.pop(_ASSET_REF_LOCAL_ID_FIELD)
        asset_ref = local_id_to_ref.get(asset_local_id)
        if asset_ref is None:
            raise ValueError(
                f"asset_ref_local_id {asset_local_id!r} does not match any entity listed "
                "earlier in this response"
            )
        content["asset_ref"] = asset_ref

    if "project_ref" in model.model_fields:
        content["project_ref"] = project_ref

    payload = {
        **content,
        "id": identity,
        "name": identity,
        "entity_type": entity_type,
        "provenance": ProvenanceState.INFERRED,
        "confidence": _clamp_confidence(item["confidence"]),
        "discovered_by": DISCOVERED_BY,
        "source_document": source_document,
        "extraction_method": ExtractionMethod.SEMANTIC_EXTRACTION,
    }
    return model(**payload)


def _validate_against_schema(
    raw: Any, prompt: ExtractionPrompt, *, source_document: str
) -> DiscoveryFailure | None:
    try:
        jsonschema.validate(raw, prompt.response_schema)
    except jsonschema.ValidationError as exc:
        return DiscoveryFailure(
            kind="schema_violation", detail=str(exc.message), source=source_document
        )
    return None


def _parse_entities(
    raw_entities: list[dict[str, Any]],
    *,
    source_document: str,
    project_ref: EntityRef,
) -> tuple[list[MetamodelEntity], dict[str, EntityRef], list[DiscoveryFailure]]:
    entities: list[MetamodelEntity] = []
    local_id_to_ref: dict[str, EntityRef] = {}
    seen_suggested_ids: set[str] = set()
    failures: list[DiscoveryFailure] = []

    for item in raw_entities:
        local_id = item["local_id"]
        suggested_id = item["suggested_id"]
        if suggested_id in seen_suggested_ids:
            failures.append(
                DiscoveryFailure(
                    kind="duplicate_suggested_id",
                    detail=f"suggested_id {suggested_id!r} used more than once in one response",
                    source=source_document,
                )
            )
            continue
        try:
            entity = _construct_entity(
                item,
                source_document=source_document,
                project_ref=project_ref,
                local_id_to_ref=local_id_to_ref,
            )
        except (ValidationError, ValueError) as exc:
            failures.append(
                DiscoveryFailure(
                    kind="entity_construction_failed",
                    detail=str(exc),
                    source=f"{source_document}#{local_id}",
                )
            )
            continue
        seen_suggested_ids.add(suggested_id)
        entities.append(entity)
        local_id_to_ref[local_id] = entity.ref()

    return entities, local_id_to_ref, failures


def parse_technical_response(
    raw: Any,
    *,
    prompt: ExtractionPrompt,
    source_document: str,
    project_ref: EntityRef,
) -> ParsedResponse:
    """Parse one technical-file extraction response."""
    schema_failure = _validate_against_schema(raw, prompt, source_document=source_document)
    if schema_failure is not None:
        return ParsedResponse(failures=[schema_failure])

    entities, local_id_to_ref, failures = _parse_entities(
        raw["entities"], source_document=source_document, project_ref=project_ref
    )

    relationships: list[RelationshipCandidate] = []
    for rel in raw["relationships"]:
        source_ref = local_id_to_ref.get(rel["source_local_id"])
        if source_ref is None:
            failures.append(
                DiscoveryFailure(
                    kind="unknown_relationship_source",
                    detail=f"relationship source_local_id {rel['source_local_id']!r} does not "
                    "match any entity constructed from this response",
                    source=source_document,
                )
            )
            continue
        relationships.append(
            RelationshipCandidate(
                type=rel["type"],
                source_ref=source_ref,
                confidence=_clamp_confidence(rel["confidence"]),
                target_kind=EntityType(rel["target_kind"]),
                target_symbolic_name=rel["target_symbolic_name"],
            )
        )

    return ParsedResponse(entities=entities, relationships=relationships, failures=failures)


def parse_delivery_response(
    raw: Any,
    *,
    prompt: ExtractionPrompt,
    source_document: str,
    project_ref: EntityRef,
    known_entities: dict[str, EntityRef],
) -> ParsedResponse:
    """Parse one delivery (Markdown) extraction response.

    `known_entities` maps id -> `EntityRef` for every entity the prompt
    offered as a legal `DESCRIBES` target. The schema already constrains
    `target_id` to this set, so a schema-conforming response's target
    string is trustworthy without a second lookup to accept it -- but the
    lookup still happens, because a client is never trusted to have actually
    enforced the schema it was asked to conform to; only what this module
    itself checks is trusted.
    """
    schema_failure = _validate_against_schema(raw, prompt, source_document=source_document)
    if schema_failure is not None:
        return ParsedResponse(failures=[schema_failure])

    entities, local_id_to_ref, failures = _parse_entities(
        raw["entities"], source_document=source_document, project_ref=project_ref
    )

    relationships: list[RelationshipCandidate] = []
    for rel in raw["relationships"]:
        source_ref = local_id_to_ref.get(rel["source_local_id"])
        if source_ref is None:
            failures.append(
                DiscoveryFailure(
                    kind="unknown_relationship_source",
                    detail=f"relationship source_local_id {rel['source_local_id']!r} does not "
                    "match any entity constructed from this response",
                    source=source_document,
                )
            )
            continue
        target_ref = known_entities.get(rel["target_id"])
        if target_ref is None:
            failures.append(
                DiscoveryFailure(
                    kind="unknown_describes_target",
                    detail=f"target_id {rel['target_id']!r} not in the known-entities index "
                    "this client was given -- rejected regardless of what schema validation "
                    "already caught",
                    source=source_document,
                )
            )
            continue
        relationships.append(
            RelationshipCandidate(
                type=rel["type"],
                source_ref=source_ref,
                confidence=_clamp_confidence(rel["confidence"]),
                target_ref=target_ref,
            )
        )

    return ParsedResponse(entities=entities, relationships=relationships, failures=failures)
