"""ProjectGraphService -- the thin front door onto a project's dual twin.

Every write still goes through ``MetadataRepository``/``GraphRepository``; every
read still returns Phase 1 entities and Phase 1 engine result types unchanged.
This service adds exactly four things persistence and the engines don't already
have on their own: registry-validated ingestion, dual-plane write consistency
(metadata and graph together, never one without the other), snapshotting, and
project-scoped access to the query facade. If a method here does anything an
engine or a repository could already do unassisted, it does not belong here.

Not a fourth persistence layer -- constructed over the same ports Phase 1
already defined, so it works identically against the in-memory adapters (used
throughout this module's own tests) and the real Neo4j/PostgreSQL adapters.
"""

from __future__ import annotations

from domain.metamodel.base import EntityRef, MetamodelEntity, utc_now
from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.entities.delivery import ApprovalGate
from domain.metamodel.entities.shared.snapshot import ProjectSnapshot
from domain.metamodel.entities.technical import Change
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import LoadedDeliveryModel, MetamodelRegistry
from domain.metamodel.relationships import Relationship
from engines.gates import GateReadiness, GateState, assess_gate
from engines.impact import ChangeImpact, TraceabilityChain, analyze_impact, trace, traceability_score
from persistence.ports import GraphRepository, MetadataRepository, StoredEntity
from project_graph.errors import IngestionError, SnapshotError, UnknownProjectError
from project_graph.snapshot import build_snapshot


class ProjectGraphService:
    """Owns the lifecycle of one or more projects' dual digital twins."""

    def __init__(self, metadata: MetadataRepository, graph: GraphRepository) -> None:
        self._metadata = metadata
        self._graph = graph

    # -- internal -----------------------------------------------------------

    def _require_project(self, project_ref: EntityRef) -> StoredEntity:
        stored = self._metadata.get(EntityType.PROJECT, project_ref.id, version=project_ref.version)
        if stored is None:
            raise UnknownProjectError(project_ref)
        return stored

    # -- lifecycle ------------------------------------------------------------

    def register_project(self, project: MetamodelEntity) -> StoredEntity:
        """Register a project. The first write in any project's lifecycle.

        A semantic entry point over ``ingest_entity`` -- projects are entities
        like any other, but this name is what a caller reaches for.
        """
        return self.ingest_entity(project)

    def ingest_entity(self, entity: MetamodelEntity) -> StoredEntity:
        """Write one entity to both planes. The path every future ingestion --
        Phase 3 discovery, manual entry, anything -- goes through.

        The ``entity_type`` check is defensive: Pydantic already guarantees it
        for any real entity instance, but this is the boundary where a future
        caller (a discovery adapter deserializing untrusted input, say) could
        hand in something malformed. Catching that here, with context, beats
        an ``AttributeError`` three calls deeper.
        """
        if entity.entity_type not in ENTITY_CLASSES:
            raise IngestionError(
                f"unknown entity type {entity.entity_type!r}; not registered in ENTITY_CLASSES"
            )
        stored = self._metadata.upsert(entity)
        self._graph.upsert_node(
            EntityRef(type=entity.entity_type, id=entity.id),
            properties={"name": entity.name, "twin": entity.twin.value},
        )
        return stored

    def ingest_relationship(self, rel: Relationship, registry: MetamodelRegistry) -> None:
        """Validate against the registry, then write to both planes.

        This is the dual-plane consistency guarantee: there is exactly one
        method that writes relationships, so nothing above the service can
        write to one plane and forget the other. The durable log (metadata
        plane) is written first, then the projection (graph plane) --
        consistent with ADR-0001's framing of which one is the source of truth.
        """
        try:
            rel.validate_against(registry)
        except ValueError as exc:
            raise IngestionError(f"relationship {rel.id} ({rel}) failed validation: {exc}") from exc
        self._metadata.upsert_relationship(rel)
        self._graph.upsert_relationship(rel)

    def rebuild_graph(self) -> int:
        """Repopulate the graph plane from the metadata plane's durable log.

        Proves ADR-0001's "the graph plane is a projection" claim with working
        code. ``GraphRepository.clear()`` empties the whole graph plane -- it
        has no project-scoping concept -- so this method necessarily operates
        globally too, from the whole durable relationship log, rather than
        pretending to isolate one project's slice of a shared graph. Returns
        the number of edges rebuilt.
        """
        self._graph.clear()
        relationships = self._metadata.all_relationships()
        for rel in relationships:
            self._graph.upsert_relationship(rel)
        return len(relationships)

    # -- snapshot -------------------------------------------------------------

    def snapshot(
        self, project_ref: EntityRef, registry: MetamodelRegistry, *, max_depth: int = 25
    ) -> ProjectSnapshot:
        """Pin a reproducible point-in-time view of one project's twin.

        Scope is the transitive closure of the project's graph node, up to
        ``max_depth``, walked in both directions. Only nodes that also have a
        row in the metadata plane are pinned into ``entity_refs`` -- a node
        reached through traversal that has no metadata row is a catalog or
        registry reference (an EngineeringRole, a Capability definition, a
        DeliveryTask template), not project-owned instance data, and those are
        already covered as a whole by ``registry_digest`` rather than pinned
        individually.

        Persisted through ``ingest_entity`` like any other entity -- a
        snapshot needs no special-cased storage.
        """
        stored_project = self._require_project(project_ref)
        pinned_project_ref = EntityRef(
            type=EntityType.PROJECT, id=project_ref.id, version=stored_project.version
        )

        discovered: dict[str, EntityRef] = {str(pinned_project_ref.identity): pinned_project_ref.identity}
        for result in self._graph.traverse(
            pinned_project_ref, max_depth=max_depth, direction="both"
        ):
            discovered.setdefault(str(result.ref), result.ref)

        entity_refs: list[EntityRef] = []
        for ref in discovered.values():
            found = self._metadata.get(ref.type, ref.id)
            if found is not None:
                entity_refs.append(EntityRef(type=ref.type, id=ref.id, version=found.version))

        relationship_ids = [
            rel.id
            for rel in self._graph.relationships()
            if str(rel.source.identity) in discovered and str(rel.target.identity) in discovered
        ]

        snapshot = build_snapshot(
            project_ref=pinned_project_ref,
            registry=registry,
            entity_refs=entity_refs,
            relationship_ids=relationship_ids,
        )
        self.ingest_entity(snapshot)
        return snapshot

    def restore_snapshot(self, snapshot: ProjectSnapshot) -> None:
        """Reconstruct the graph plane exactly as a snapshot pinned it.

        Rebuilds from the pinned relationship ids *only* -- never whatever
        relationships exist now -- because the point is reconstructing what
        existed *then*. Fails loudly, before touching the graph, if anything
        pinned has since been deleted: a snapshot that quietly restores only
        part of what it pinned is worse than one that refuses, because it
        looks trustworthy while being wrong.
        """
        missing_entities = [
            ref
            for ref in snapshot.entity_refs
            if self._metadata.get(ref.type, ref.id, version=ref.version) is None
        ]
        if missing_entities:
            raise SnapshotError(
                f"cannot restore snapshot {snapshot.id}: {len(missing_entities)} pinned "
                f"entities no longer exist in the metadata plane: "
                f"{[str(r) for r in missing_entities[:5]]}"
            )

        by_id = {rel.id: rel for rel in self._metadata.all_relationships()}
        missing_relationships = [rid for rid in snapshot.relationship_ids if rid not in by_id]
        if missing_relationships:
            raise SnapshotError(
                f"cannot restore snapshot {snapshot.id}: {len(missing_relationships)} pinned "
                f"relationships no longer exist in the durable log: {missing_relationships[:5]}"
            )

        self._graph.clear()
        for ref in snapshot.entity_refs:
            self._graph.upsert_node(ref.identity)
        for rid in snapshot.relationship_ids:
            self._graph.upsert_relationship(by_id[rid])

    # -- query facade -----------------------------------------------------

    def analyze_change(
        self, change: Change, delivery_model: LoadedDeliveryModel, **kwargs: object
    ) -> ChangeImpact:
        """Dual impact analysis, scoped to this service's graph.

        Thin wrapper over ``engines.impact.analyze_impact`` -- the value is
        that a caller supplies a domain object, not a ``GraphRepository``.
        """
        return analyze_impact(change, self._graph, delivery_model, **kwargs)  # type: ignore[arg-type]

    def trace_requirement(self, ref: EntityRef, **kwargs: object) -> TraceabilityChain:
        """Traceability chain resolution, scoped to this service's graph."""
        return trace(ref, self._graph, **kwargs)  # type: ignore[arg-type]

    def assess_traceability(self, starts: list[EntityRef], **kwargs: object) -> float:
        """Mean traceability completeness across several starting points,
        scoped to this service's graph.

        Thin wrapper over ``engines.impact.traceability_score`` -- the fourth
        query-facade method, completing the pair with ``trace_requirement``
        (single ref) the same way ``analyze_change`` and ``assess_readiness``
        already pair technical/delivery impact with gate readiness. Feeds
        ``GateState.traceability`` directly (``orchestrator/gate.py``, Phase 6).
        """
        return traceability_score(starts, self._graph, **kwargs)  # type: ignore[arg-type]

    def assess_readiness(
        self, gate: ApprovalGate, state: GateState, **kwargs: object
    ) -> GateReadiness:
        """Gate readiness assessment.

        ``GateState`` is still assembled by the caller for four of its six
        fields -- ``present_artifact_kinds``, ``checklist_outcomes``,
        ``satisfied_evidence`` and ``approvals`` have no real assembler
        anywhere in this codebase, a deliberate boundary (see
        ``docs/orchestrator.md``'s "what this is not"). ``passed_evaluations``
        (``engines.evaluation.passed_evaluation_keys``, Phase 5) and
        ``traceability`` (this service's own ``assess_traceability``, Phase 6)
        do have real assemblers now -- ``orchestrator/gate.py`` wires both
        from actual graph/metadata state before calling this method. Wrapping
        the call is still worth it: one import (``project_graph``) instead of
        three, and symmetry with the other three facade methods.
        """
        return assess_gate(gate, state, **kwargs)  # type: ignore[arg-type]
