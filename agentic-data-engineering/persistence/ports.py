"""Persistence ports: the contracts both planes are written against.

Two planes, two jobs (ADR-0001):

* **Metadata plane** (PostgreSQL) -- transactional system of record for entity
  *state*: versioned rows, the durable relationship log, gate assessments, and
  an append-only audit ledger.
* **Graph plane** (Neo4j) -- query system of record for *relationships*: the
  dual digital twin that impact analysis, traceability and lineage traverse. A
  projection, rebuildable from the metadata plane.

Both are Protocols with an in-memory implementation, so nothing above this layer
knows which database is behind it and the unit suite needs no infrastructure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel
from domain.metamodel.entities.shared.work import Decision
from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import Relationship


class StoredEntity(MetamodelModel):
    """An entity as it sits in the metadata plane.

    The payload stays a plain dict rather than a typed model so a row written
    under an older metamodel version can still be read, inspected and migrated
    instead of failing to deserialize.
    """

    entity_type: EntityType
    entity_id: str
    version: str
    metamodel_version: str
    payload: dict[str, object]
    content_hash: str
    is_current: bool = True


class AuditEntry(MetamodelModel):
    """One link in the append-only, hash-chained audit ledger."""

    sequence: int = Field(ge=0)
    decision_id: str
    entry_hash: str
    previous_hash: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class TraversalResult(MetamodelModel):
    """One node reached during a graph traversal.

    ``confidence`` is the product of confidences along the path taken, so a node
    reached through two INFERRED hops is visibly less certain than one reached
    through an OBSERVED edge. Impact analysis ranks on this, and it matters
    doubly for cross-twin edges: a low-confidence ``DESCRIBES`` should not send
    someone to update a document that was never about their code.
    """

    ref: EntityRef
    depth: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    path: list[str] = Field(default_factory=list)


@runtime_checkable
class MetadataRepository(Protocol):
    """Transactional store for entity state and the audit ledger."""

    def upsert(self, entity: object) -> StoredEntity:
        """Write an entity version. Re-writing an identical version is a no-op."""
        ...

    def get(
        self, entity_type: EntityType, entity_id: str, version: str | None = None
    ) -> StoredEntity | None:
        """Fetch one entity. ``version=None`` returns the current version."""
        ...

    def list(self, entity_type: EntityType, *, current_only: bool = True) -> list[StoredEntity]:
        ...

    def versions(self, entity_type: EntityType, entity_id: str) -> list[str]:
        """All stored versions of an entity, oldest first."""
        ...

    def delete(self, entity_type: EntityType, entity_id: str, version: str | None = None) -> bool:
        ...

    def upsert_relationship(self, rel: Relationship) -> None:
        """Write an edge to the durable relationship log.

        This is the metadata plane's half of ADR-0001's "the graph plane is a
        projection" claim: the graph store can be dropped and rebuilt from what
        this method persists. Identified by the same natural key as the graph
        plane -- (source, type, target) -- so re-writing an edge updates it.
        """
        ...

    def all_relationships(self) -> list[Relationship]:
        """Every stored edge -- the input to rebuilding the graph plane."""
        ...

    def append_audit(self, decision: Decision) -> AuditEntry:
        """Append a decision to the ledger. There is deliberately no update."""
        ...

    def audit_entries(self) -> list[AuditEntry]:
        ...

    def verify_audit_chain(self) -> bool:
        """Whether the ledger's hash chain is intact."""
        ...


@runtime_checkable
class GraphRepository(Protocol):
    """Traversal store for the dual digital twin."""

    def upsert_node(self, ref: EntityRef, *, properties: dict[str, object] | None = None) -> None:
        ...

    def upsert_relationship(self, rel: Relationship) -> None:
        """Write an edge. Edges are identified by (source, type, target)."""
        ...

    def get_relationship(
        self, source: EntityRef, type_: str, target: EntityRef
    ) -> Relationship | None:
        ...

    def relationships(
        self,
        *,
        source: EntityRef | None = None,
        target: EntityRef | None = None,
        type_: str | None = None,
    ) -> list[Relationship]:
        ...

    def neighbors(
        self, ref: EntityRef, *, type_: str | None = None, direction: str = "outgoing"
    ) -> list[EntityRef]:
        """Directly connected nodes. ``direction`` is outgoing, incoming or both."""
        ...

    def traverse(
        self,
        start: EntityRef,
        *,
        relationship_types: list[str] | None = None,
        max_depth: int = 3,
        min_confidence: float = 0.0,
        direction: str = "incoming",
    ) -> list[TraversalResult]:
        """Walk the graph from ``start``, degrading confidence along each hop.

        The default direction is *incoming* because the commonest question is
        "what depends on this thing that just changed?" rather than "what does
        this thing depend on".
        """
        ...

    def clear(self) -> None:
        ...
