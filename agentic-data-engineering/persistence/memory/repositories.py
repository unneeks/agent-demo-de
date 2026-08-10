"""In-memory adapters -- the reference implementation and the test default.

Not mocks. They implement the same contract as the Neo4j and PostgreSQL
adapters and are exercised by the same contract suite, which is what lets the
unit tests run in milliseconds while still meaning something. When a real
adapter's behaviour is ambiguous, this is the specification.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.shared.work import Decision
from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import Relationship
from domain.metamodel.version import METAMODEL_VERSION
from persistence.ports import AuditEntry, StoredEntity, TraversalResult

_GENESIS_HASH = "0" * 64
_DIRECTIONS = ("outgoing", "incoming", "both")


def content_hash(payload: dict[str, Any]) -> str:
    """Stable digest of an entity payload.

    ``sort_keys`` plus ``default=str`` makes the digest independent of dict
    ordering and safe for datetimes and enums, so the same entity always hashes
    the same way regardless of how it was constructed.
    """
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class InMemoryMetadataRepository:
    """Entity state and audit ledger, held in dictionaries."""

    def __init__(self) -> None:
        self._entities: dict[tuple[EntityType, str, str], StoredEntity] = {}
        self._audit: list[AuditEntry] = []
        self._relationships: dict[tuple[str, str, str], Relationship] = {}

    def upsert(self, entity: object) -> StoredEntity:
        payload = entity.model_dump(mode="json")  # type: ignore[attr-defined]
        entity_type = EntityType(payload["entity_type"])
        entity_id = str(payload["id"])
        version = str(payload.get("version", "0.1.0"))

        stored = StoredEntity(
            entity_type=entity_type,
            entity_id=entity_id,
            version=version,
            metamodel_version=str(payload.get("metamodel_version", METAMODEL_VERSION)),
            payload=payload,
            content_hash=content_hash(payload),
            is_current=True,
        )

        # Only one version of an entity is current at a time.
        for key, existing in list(self._entities.items()):
            if key[0] == entity_type and key[1] == entity_id and existing.is_current:
                self._entities[key] = existing.model_copy(update={"is_current": False})

        self._entities[(entity_type, entity_id, version)] = stored
        return stored

    def get(
        self, entity_type: EntityType, entity_id: str, version: str | None = None
    ) -> StoredEntity | None:
        if version is not None:
            return self._entities.get((entity_type, entity_id, version))
        current = [
            e
            for (t, i, _), e in self._entities.items()
            if t == entity_type and i == entity_id and e.is_current
        ]
        return current[0] if current else None

    def list(self, entity_type: EntityType, *, current_only: bool = True) -> list[StoredEntity]:
        results = [e for (t, _, _), e in self._entities.items() if t == entity_type]
        if current_only:
            results = [e for e in results if e.is_current]
        return sorted(results, key=lambda e: (e.entity_id, e.version))

    def versions(self, entity_type: EntityType, entity_id: str) -> list[str]:
        return sorted(v for (t, i, v) in self._entities if t == entity_type and i == entity_id)

    def delete(self, entity_type: EntityType, entity_id: str, version: str | None = None) -> bool:
        keys = [
            k
            for k in self._entities
            if k[0] == entity_type and k[1] == entity_id and (version is None or k[2] == version)
        ]
        for key in keys:
            del self._entities[key]
        return bool(keys)

    def upsert_relationship(self, rel: Relationship) -> None:
        """Write to the durable relationship log.

        Keyed identically to how the graph plane keys edges -- ``rel.key`` is
        ``(source identity, type, target identity)`` -- so the two planes agree
        on what "the same edge" means.
        """
        self._relationships[rel.key] = rel

    def all_relationships(self) -> list[Relationship]:
        return sorted(self._relationships.values(), key=lambda r: r.key)

    def append_audit(self, decision: Decision) -> AuditEntry:
        """Append to the hash-chained ledger.

        There is no corresponding update or delete, by design: the ledger is the
        record a reviewer relies on, so it only ever grows.
        """
        previous = self._audit[-1].entry_hash if self._audit else _GENESIS_HASH
        payload = decision.model_dump(mode="json")
        entry_hash = hashlib.sha256((previous + content_hash(payload)).encode("utf-8")).hexdigest()
        entry = AuditEntry(
            sequence=len(self._audit),
            decision_id=decision.id,
            entry_hash=entry_hash,
            previous_hash=None if not self._audit else previous,
            payload=payload,
        )
        self._audit.append(entry)
        return entry

    def audit_entries(self) -> list[AuditEntry]:
        return list(self._audit)

    def verify_audit_chain(self) -> bool:
        previous = _GENESIS_HASH
        for entry in self._audit:
            expected = hashlib.sha256(
                (previous + content_hash(entry.payload)).encode("utf-8")
            ).hexdigest()
            if expected != entry.entry_hash:
                return False
            previous = entry.entry_hash
        return True


class InMemoryGraphRepository:
    """The dual digital twin, held as an adjacency map."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[tuple[str, str, str], Relationship] = {}
        self._out: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        self._in: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    @staticmethod
    def _node_key(ref: EntityRef) -> str:
        """Nodes are identified by type and id, never by version.

        A node is the *thing*; versioned state lives in the metadata plane.
        Keying the graph by version would fragment the twin into one island per
        release.
        """
        return f"{ref.type.value}:{ref.id}"

    @staticmethod
    def _identity_ref(ref: EntityRef) -> EntityRef:
        """Strip the version, yielding what the graph actually keys on.

        Returning a version-pinned ref would mean two edges into the same node
        produced refs that compare unequal while denoting one node. The Neo4j
        adapter rebuilds refs from node properties, which carry no version, so
        this keeps the two adapters answering identically.
        """
        return ref.identity

    def upsert_node(self, ref: EntityRef, *, properties: dict[str, Any] | None = None) -> None:
        key = self._node_key(ref)
        node = self._nodes.setdefault(key, {"type": ref.type.value, "id": ref.id})
        if properties:
            node.update(properties)

    def upsert_relationship(self, rel: Relationship) -> None:
        self.upsert_node(rel.source)
        self.upsert_node(rel.target)
        key = (self._node_key(rel.source), rel.type, self._node_key(rel.target))
        if key not in self._edges:
            self._out[key[0]].append(key)
            self._in[key[2]].append(key)
        self._edges[key] = rel

    def get_relationship(
        self, source: EntityRef, type_: str, target: EntityRef
    ) -> Relationship | None:
        return self._edges.get((self._node_key(source), type_, self._node_key(target)))

    def relationships(
        self,
        *,
        source: EntityRef | None = None,
        target: EntityRef | None = None,
        type_: str | None = None,
    ) -> list[Relationship]:
        results = [
            rel
            for (s, t, tgt), rel in self._edges.items()
            if (source is None or s == self._node_key(source))
            and (target is None or tgt == self._node_key(target))
            and (type_ is None or t == type_)
        ]
        return sorted(results, key=lambda r: (str(r.source), r.type, str(r.target)))

    def neighbors(
        self, ref: EntityRef, *, type_: str | None = None, direction: str = "outgoing"
    ) -> list[EntityRef]:
        if direction not in _DIRECTIONS:
            raise ValueError(f"direction must be outgoing, incoming or both; got {direction!r}")
        seen: dict[str, EntityRef] = {}
        key = self._node_key(ref)
        if direction in ("outgoing", "both"):
            for edge_key in self._out.get(key, []):
                if type_ is None or edge_key[1] == type_:
                    rel = self._edges[edge_key]
                    seen[self._node_key(rel.target)] = self._identity_ref(rel.target)
        if direction in ("incoming", "both"):
            for edge_key in self._in.get(key, []):
                if type_ is None or edge_key[1] == type_:
                    rel = self._edges[edge_key]
                    seen[self._node_key(rel.source)] = self._identity_ref(rel.source)
        return [seen[k] for k in sorted(seen)]

    def traverse(
        self,
        start: EntityRef,
        *,
        relationship_types: list[str] | None = None,
        max_depth: int = 3,
        min_confidence: float = 0.0,
        direction: str = "incoming",
    ) -> list[TraversalResult]:
        """Breadth-first walk that multiplies confidence along each hop.

        Two hops through inferred edges at 0.8 each yields 0.64, so a caller can
        cut off speculative reach with ``min_confidence`` rather than treating
        every reachable node as equally impacted. When a node is reachable by
        several paths the most confident one wins.
        """
        if direction not in _DIRECTIONS:
            raise ValueError(f"direction must be outgoing, incoming or both; got {direction!r}")

        best: dict[str, TraversalResult] = {}
        frontier: list[TraversalResult] = [
            TraversalResult(ref=self._identity_ref(start), depth=0, confidence=1.0, path=[])
        ]
        start_key = self._node_key(start)

        while frontier:
            current = frontier.pop(0)
            if current.depth >= max_depth:
                continue
            key = self._node_key(current.ref)
            edge_keys: list[tuple[str, str, str]] = []
            if direction in ("outgoing", "both"):
                edge_keys += self._out.get(key, [])
            if direction in ("incoming", "both"):
                edge_keys += self._in.get(key, [])

            for edge_key in edge_keys:
                rel = self._edges[edge_key]
                if relationship_types and rel.type not in relationship_types:
                    continue
                # Structural edges carry no confidence; treat them as certain.
                hop_confidence = 1.0 if rel.confidence is None else rel.confidence
                confidence = current.confidence * hop_confidence
                if confidence < min_confidence:
                    continue

                next_ref = self._identity_ref(rel.source if edge_key[2] == key else rel.target)
                next_key = self._node_key(next_ref)
                if next_key == start_key:
                    continue

                candidate = TraversalResult(
                    ref=next_ref,
                    depth=current.depth + 1,
                    confidence=confidence,
                    path=[*current.path, rel.type],
                )
                existing = best.get(next_key)
                if existing is None or candidate.confidence > existing.confidence:
                    best[next_key] = candidate
                    frontier.append(candidate)

        return sorted(best.values(), key=lambda r: (-r.confidence, r.depth, str(r.ref)))

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._out.clear()
        self._in.clear()
