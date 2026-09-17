"""`discover_project` -- the entry point wiring registration, extraction, and
ingestion through `ProjectGraphService`.

Four passes: technical-file extraction; delivery-file extraction (given the
entity index technical extraction built); deterministic resolution of every
relationship candidate from both passes against that same index (a
technical candidate resolves symbolically, a delivery/`DESCRIBES` candidate
already carries a resolved target and passes through unchanged); and
ingestion of everything through the service. Every write still goes through
`ingest_entity`/`ingest_relationship` -- this module never touches
`persistence.ports` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from domain.metamodel.base import EntityRef, MetamodelEntity
from domain.metamodel.entities.technical import Project, Repository
from domain.metamodel.enums import EntityType, ProvenanceState
from domain.metamodel.registry import MetamodelRegistry
from domain.metamodel.relationships import relationship
from project_graph.errors import IngestionError
from project_graph.service import ProjectGraphService

from discovery.extraction.client import ExtractionClient
from discovery.extraction.parse_response import (
    RelationshipCandidate,
    parse_delivery_response,
    parse_technical_response,
)
from discovery.extraction.prompts import (
    DESCRIBES_LEGAL_TARGET_TYPES,
    SOURCE_KIND_ENTITY_TYPES,
    KnownEntity,
    build_delivery_prompt,
    build_technical_prompt,
)
from discovery.resolve import build_entity_index, resolve_relationship_candidates
from discovery.result import DiscoveryFailure, DiscoveryReport, DiscoverySkip
from discovery.walk import MARKDOWN, TECHNICAL_SOURCE_KINDS, discover_candidate_files

#: Structural fact synthesized by this module, never asked of the agent:
#: which entities a walked file's extraction produced belongs to the
#: repository that was walked. Directly observable once a file is known to
#: have produced an entity -- not content interpretation.
_WALK_DISCOVERED_BY = "discovery-walk@0.1.0"

#: `CONTAINS`' legal target types (`metamodel-registry/relationship_types.yaml`).
#: `SchemaDefinition` and `DeliveryArtifact` are deliberately absent -- they
#: are reached via `HAS_SCHEMA`/`DESCRIBES` instead, not containment.
_CONTAINS_LEGAL_TARGET_TYPES = frozenset(
    {
        EntityType.REPOSITORY,
        EntityType.CODE_ARTIFACT,
        EntityType.DATA_ASSET,
        EntityType.PIPELINE,
        EntityType.TEST,
        EntityType.TASK,
        EntityType.INFRASTRUCTURE,
    }
)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _build_repository(*, repository_id: str, project_ref: EntityRef) -> Repository:
    """The repository being walked is platform-known, not agent-derived --
    the same reasoning `project_ref` injection uses in `parse_response.py`.
    """
    return Repository(
        id=repository_id,
        name=repository_id,
        entity_type=EntityType.REPOSITORY,
        project_ref=project_ref,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by=_WALK_DISCOVERED_BY,
    )


class _Accumulator:
    """Mutable state threaded through one `discover_project` run."""

    def __init__(self) -> None:
        self.entities: list[MetamodelEntity] = []
        self.entity_source_path: dict[tuple[EntityType, str], str] = {}
        self.relationship_candidates: list[RelationshipCandidate] = []
        self.skipped: list[DiscoverySkip] = []
        self.failed: list[DiscoveryFailure] = []

    def add_parsed(
        self, parsed, *, source_document: str, on_error: Literal["fail_fast", "collect"]
    ) -> None:
        for entity in parsed.entities:
            self.entities.append(entity)
            self.entity_source_path[(entity.entity_type, entity.id)] = source_document
        self.relationship_candidates.extend(parsed.relationships)
        self.failed.extend(parsed.failures)
        if on_error == "fail_fast" and parsed.failures:
            first = parsed.failures[0]
            raise IngestionError(
                f"extraction of {source_document} failed ({first.kind}): {first.detail}"
            )


def discover_project(
    service: ProjectGraphService,
    registry: MetamodelRegistry,
    project: Project,
    client: ExtractionClient,
    *,
    repository_root: Path,
    repository_id: str | None = None,
    on_error: Literal["fail_fast", "collect"] = "collect",
) -> DiscoveryReport:
    """Discover `repository_root`'s twin and ingest it through `service`.

    `on_error="collect"` (default) records a failure and continues past it:
    `ProjectGraphService` calls are atomic per-call, not across a run, so
    discarding already-good writes because a later file failed would be
    strictly worse than reporting an itemized gap. `"fail_fast"` re-raises
    the underlying error immediately instead.
    """
    stored_project = service.register_project(project)
    project_ref = EntityRef(type=stored_project.entity_type, id=stored_project.entity_id)
    repository_ref_id = repository_id or repository_root.name
    repository = _build_repository(repository_id=repository_ref_id, project_ref=project_ref)

    accumulator = _Accumulator()
    accumulator.entities.append(repository)
    accumulator.entity_source_path[(repository.entity_type, repository.id)] = "."

    candidates = discover_candidate_files(repository_root)

    # -- pass 1: technical-file extraction -----------------------------------
    for candidate in candidates:
        if candidate.source_kind not in TECHNICAL_SOURCE_KINDS:
            continue  # Markdown (or any future non-technical kind) is pass 3's job.

        entity_types = SOURCE_KIND_ENTITY_TYPES.get(candidate.source_kind, ())
        if not entity_types:
            accumulator.skipped.append(
                DiscoverySkip(
                    kind="no_target_entity_type",
                    detail=f"source_kind {candidate.source_kind!r} has no legal target entity "
                    "type in the metamodel today",
                    source=candidate.path.as_posix(),
                )
            )
            continue

        content = _read_text(candidate.absolute_path)
        if content is None:
            accumulator.skipped.append(
                DiscoverySkip(
                    kind="unreadable_file", detail="could not decode as UTF-8", source=candidate.path.as_posix()
                )
            )
            continue

        prompt = build_technical_prompt(
            relative_path=candidate.path, content=content, source_kind=candidate.source_kind
        )
        raw = client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)
        parsed = parse_technical_response(
            raw, prompt=prompt, source_document=candidate.path.as_posix(), project_ref=project_ref
        )
        accumulator.add_parsed(
            parsed, source_document=candidate.path.as_posix(), on_error=on_error
        )

    # Known-entities index for pass 3, built from pass 1's output only --
    # delivery entities are never legal `DESCRIBES` targets themselves.
    known_entities = [
        KnownEntity(
            ref=entity.ref(),
            entity_type=entity.entity_type,
            name=entity.name,
            path=accumulator.entity_source_path.get((entity.entity_type, entity.id)),
        )
        for entity in accumulator.entities
        if entity.entity_type in DESCRIBES_LEGAL_TARGET_TYPES
    ]
    known_entity_refs = {entry.ref.id: entry.ref for entry in known_entities}

    # -- pass 3: delivery-file extraction, given the technical index above --
    for candidate in candidates:
        if candidate.source_kind != MARKDOWN:
            continue
        content = _read_text(candidate.absolute_path)
        if content is None:
            accumulator.skipped.append(
                DiscoverySkip(
                    kind="unreadable_file", detail="could not decode as UTF-8", source=candidate.path.as_posix()
                )
            )
            continue
        prompt = build_delivery_prompt(
            relative_path=candidate.path, content=content, known_entities=known_entities
        )
        raw = client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)
        parsed = parse_delivery_response(
            raw,
            prompt=prompt,
            source_document=candidate.path.as_posix(),
            project_ref=project_ref,
            known_entities=known_entity_refs,
        )
        accumulator.add_parsed(
            parsed, source_document=candidate.path.as_posix(), on_error=on_error
        )

    # -- pass 2 (deterministic resolution), run once over every candidate ---
    # produced by both passes: a technical candidate resolves symbolically
    # against the full entity index; a delivery/DESCRIBES candidate already
    # carries a resolved `target_ref` and passes through unchanged.
    entity_index = build_entity_index(accumulator.entities)
    resolved_relationships, resolution_skips = resolve_relationship_candidates(
        accumulator.relationship_candidates, entity_index
    )
    accumulator.skipped.extend(resolution_skips)

    # Deterministic structural CONTAINS edges: repository -> everything it
    # produced (legal target types only), project -> repository. Never
    # asked of the agent -- fully knowable from which file produced which
    # entity, already tracked in entity_source_path.
    contains_edges = [
        relationship(
            "CONTAINS", project_ref, repository.ref(), discovered_by=_WALK_DISCOVERED_BY
        )
    ]
    for entity in accumulator.entities:
        if entity is repository:
            continue
        if entity.entity_type in _CONTAINS_LEGAL_TARGET_TYPES:
            contains_edges.append(
                relationship(
                    "CONTAINS", repository.ref(), entity.ref(), discovered_by=_WALK_DISCOVERED_BY
                )
            )

    # -- pass 4: ingestion ----------------------------------------------------
    ingested_keys: set[tuple[EntityType, str]] = {(project_ref.type, project_ref.id)}
    entities_by_type: dict[EntityType, int] = {}
    entities_ingested = 0

    def _ingest_entity(entity: MetamodelEntity) -> None:
        nonlocal entities_ingested
        try:
            service.ingest_entity(entity)
        except IngestionError as exc:
            accumulator.failed.append(
                DiscoveryFailure(
                    kind="ingest_entity_failed",
                    detail=str(exc),
                    source=f"{entity.entity_type.value}:{entity.id}",
                )
            )
            if on_error == "fail_fast":
                raise
            return
        ingested_keys.add((entity.entity_type, entity.id))
        entities_by_type[entity.entity_type] = entities_by_type.get(entity.entity_type, 0) + 1
        entities_ingested += 1

    for entity in accumulator.entities:
        _ingest_entity(entity)

    relationships_ingested = 0
    all_relationships = [*contains_edges, *resolved_relationships]
    for rel in all_relationships:
        source_key = (rel.source.type, rel.source.id)
        target_key = (rel.target.type, rel.target.id)
        if source_key not in ingested_keys or target_key not in ingested_keys:
            accumulator.failed.append(
                DiscoveryFailure(
                    kind="skipped_dangling_relationship",
                    detail=f"{rel.type}: an endpoint was never successfully ingested this run",
                    source=str(rel),
                )
            )
            continue
        try:
            service.ingest_relationship(rel, registry)
        except IngestionError as exc:
            accumulator.failed.append(
                DiscoveryFailure(kind="ingest_relationship_failed", detail=str(exc), source=str(rel))
            )
            if on_error == "fail_fast":
                raise
            continue
        relationships_ingested += 1

    return DiscoveryReport(
        project_ref=project_ref,
        entities_ingested=entities_ingested,
        relationships_ingested=relationships_ingested,
        entities_by_type=entities_by_type,
        skipped=accumulator.skipped,
        failed=accumulator.failed,
    )
