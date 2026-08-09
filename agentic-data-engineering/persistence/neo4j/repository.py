"""Neo4j adapter for the graph plane.

One deliberate modelling choice: every edge is stored as ``:RELATES`` with the
real type in a ``rel_type`` property, rather than as a native Neo4j relationship
type. Cypher cannot parameterize relationship types, so native typing would mean
interpolating a registry-supplied string into query text on every write -- an
injection surface, and a guarantee that adding a relationship type to YAML
requires new code to build the Cypher. Filtering on an indexed property costs
little and keeps the vocabulary in data where ADR-0004 puts it.

The driver is imported lazily so this module can be imported -- and the rest of
the suite can run -- without the ``neo4j`` extra installed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType, ExtractionMethod, ProvenanceState
from domain.metamodel.relationships import Relationship
from persistence.ports import TraversalResult

_DIRECTIONS = ("outgoing", "incoming", "both")


class Neo4jUnavailableError(RuntimeError):
    """The neo4j driver is not installed, or the server is unreachable."""


class Neo4jGraphRepository:
    """Graph-plane adapter. Implements the ``GraphRepository`` protocol."""

    def __init__(self, uri: str, user: str, password: str, *, database: str = "neo4j") -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise Neo4jUnavailableError(
                "the neo4j driver is not installed; install with the 'neo4j' extra"
            ) from exc
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> Neo4jGraphRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- helpers ----------------------------------------------------------

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session(database=self._database) as session:
            return [record.data() for record in session.run(query, **params)]

    @staticmethod
    def _edge_properties(rel: Relationship) -> dict[str, Any]:
        return {
            "relationship_id": rel.id,
            "rel_type": rel.type,
            "provenance": rel.provenance.value,
            "confidence": rel.confidence,
            "discovered_by": rel.discovered_by,
            "discovered_at": rel.discovered_at.isoformat(),
            "valid_from": rel.valid_from.isoformat() if rel.valid_from else None,
            "valid_until": rel.valid_until.isoformat() if rel.valid_until else None,
            "human_verified_by": rel.human_verified_by,
            "human_verified_at": (
                rel.human_verified_at.isoformat() if rel.human_verified_at else None
            ),
            "source_document": rel.source_document,
            "source_section": rel.source_section,
            "extraction_method": (
                rel.extraction_method.value if rel.extraction_method else None
            ),
            **{f"attr_{k}": v for k, v in rel.attributes.items()},
        }

    @staticmethod
    def _to_relationship(
        props: dict[str, Any], source: EntityRef, target: EntityRef
    ) -> Relationship:
        return Relationship(
            id=props["relationship_id"],
            type=props["rel_type"],
            source=source,
            target=target,
            provenance=ProvenanceState(props["provenance"]),
            confidence=props.get("confidence"),
            discovered_by=props.get("discovered_by"),
            discovered_at=datetime.fromisoformat(props["discovered_at"]),
            human_verified_by=props.get("human_verified_by"),
            human_verified_at=(
                datetime.fromisoformat(props["human_verified_at"])
                if props.get("human_verified_at")
                else None
            ),
            source_document=props.get("source_document"),
            source_section=props.get("source_section"),
            extraction_method=(
                ExtractionMethod(props["extraction_method"])
                if props.get("extraction_method")
                else None
            ),
            attributes={
                k.removeprefix("attr_"): v for k, v in props.items() if k.startswith("attr_")
            },
        )

    @staticmethod
    def _ref(data: dict[str, Any]) -> EntityRef:
        return EntityRef(type=EntityType(data["entity_type"]), id=data["entity_id"])

    # -- writes -----------------------------------------------------------

    def apply_constraints(self, cypher_path: str | None = None) -> None:
        """Apply ``constraints.cypher``. Safe to run repeatedly."""
        path = Path(cypher_path) if cypher_path else Path(__file__).parent / "constraints.cypher"
        statements = [
            s.strip()
            for s in path.read_text(encoding="utf-8").split(";")
            if s.strip() and not s.strip().startswith("//")
        ]
        for statement in statements:
            self._run(statement)

    def upsert_node(self, ref: EntityRef, *, properties: dict[str, Any] | None = None) -> None:
        self._run(
            """
            MERGE (n:Entity {entity_type: $entity_type, entity_id: $entity_id})
            SET n += $properties
            """,
            entity_type=ref.type.value,
            entity_id=ref.id,
            properties=properties or {},
        )

    def upsert_relationship(self, rel: Relationship) -> None:
        self._run(
            """
            MERGE (s:Entity {entity_type: $source_type, entity_id: $source_id})
            MERGE (t:Entity {entity_type: $target_type, entity_id: $target_id})
            MERGE (s)-[r:RELATES {rel_type: $rel_type}]->(t)
            SET r += $properties
            """,
            source_type=rel.source.type.value,
            source_id=rel.source.id,
            target_type=rel.target.type.value,
            target_id=rel.target.id,
            rel_type=rel.type,
            properties=self._edge_properties(rel),
        )

    # -- reads ------------------------------------------------------------

    def get_relationship(
        self, source: EntityRef, type_: str, target: EntityRef
    ) -> Relationship | None:
        rows = self._run(
            """
            MATCH (s:Entity {entity_type: $source_type, entity_id: $source_id})
                  -[r:RELATES {rel_type: $rel_type}]->
                  (t:Entity {entity_type: $target_type, entity_id: $target_id})
            RETURN properties(r) AS props
            """,
            source_type=source.type.value,
            source_id=source.id,
            target_type=target.type.value,
            target_id=target.id,
            rel_type=type_,
        )
        return (
            self._to_relationship(rows[0]["props"], source.identity, target.identity)
            if rows
            else None
        )

    def relationships(
        self,
        *,
        source: EntityRef | None = None,
        target: EntityRef | None = None,
        type_: str | None = None,
    ) -> list[Relationship]:
        rows = self._run(
            """
            MATCH (s:Entity)-[r:RELATES]->(t:Entity)
            WHERE ($source_id IS NULL OR (s.entity_id = $source_id AND s.entity_type = $source_type))
              AND ($target_id IS NULL OR (t.entity_id = $target_id AND t.entity_type = $target_type))
              AND ($rel_type  IS NULL OR r.rel_type = $rel_type)
            RETURN properties(r) AS props,
                   properties(s) AS source_node,
                   properties(t) AS target_node
            """,
            source_id=source.id if source else None,
            source_type=source.type.value if source else None,
            target_id=target.id if target else None,
            target_type=target.type.value if target else None,
            rel_type=type_,
        )
        results = [
            self._to_relationship(
                row["props"], self._ref(row["source_node"]), self._ref(row["target_node"])
            )
            for row in rows
        ]
        return sorted(results, key=lambda r: (str(r.source), r.type, str(r.target)))

    def neighbors(
        self, ref: EntityRef, *, type_: str | None = None, direction: str = "outgoing"
    ) -> list[EntityRef]:
        if direction not in _DIRECTIONS:
            raise ValueError(f"direction must be outgoing, incoming or both; got {direction!r}")
        patterns = {
            "outgoing": "MATCH (n:Entity {entity_type: $entity_type, entity_id: $entity_id})-[r:RELATES]->(m:Entity)",
            "incoming": "MATCH (n:Entity {entity_type: $entity_type, entity_id: $entity_id})<-[r:RELATES]-(m:Entity)",
            "both": "MATCH (n:Entity {entity_type: $entity_type, entity_id: $entity_id})-[r:RELATES]-(m:Entity)",
        }
        rows = self._run(
            f"""
            {patterns[direction]}
            WHERE $rel_type IS NULL OR r.rel_type = $rel_type
            RETURN DISTINCT properties(m) AS node
            """,
            entity_type=ref.type.value,
            entity_id=ref.id,
            rel_type=type_,
        )
        return sorted({self._ref(row["node"]) for row in rows}, key=str)

    def traverse(
        self,
        start: EntityRef,
        *,
        relationship_types: list[str] | None = None,
        max_depth: int = 3,
        min_confidence: float = 0.0,
        direction: str = "incoming",
    ) -> list[TraversalResult]:
        """Variable-length walk scoring each path by the product of its hops.

        ``coalesce(confidence, 1.0)`` treats structural edges, which carry no
        confidence, as certain -- matching the in-memory adapter exactly, which
        is what lets one contract suite cover both.
        """
        if direction not in _DIRECTIONS:
            raise ValueError(f"direction must be outgoing, incoming or both; got {direction!r}")
        arrow = {
            "outgoing": f"-[rels:RELATES*1..{max_depth}]->",
            "incoming": f"<-[rels:RELATES*1..{max_depth}]-",
            "both": f"-[rels:RELATES*1..{max_depth}]-",
        }

        rows = self._run(
            f"""
            MATCH path = (n:Entity {{entity_type: $entity_type, entity_id: $entity_id}})
                         {arrow[direction]}(m:Entity)
            WHERE ($rel_types IS NULL OR all(r IN rels WHERE r.rel_type IN $rel_types))
              AND NOT (m.entity_type = $entity_type AND m.entity_id = $entity_id)
            WITH m,
                 reduce(c = 1.0, r IN rels | c * coalesce(r.confidence, 1.0)) AS confidence,
                 length(path) AS depth,
                 [r IN rels | r.rel_type] AS rel_path
            WHERE confidence >= $min_confidence
            RETURN properties(m) AS node, confidence, depth, rel_path
            ORDER BY confidence DESC, depth ASC
            """,
            entity_type=start.type.value,
            entity_id=start.id,
            rel_types=relationship_types,
            min_confidence=min_confidence,
        )

        best: dict[str, TraversalResult] = {}
        for row in rows:
            ref = self._ref(row["node"])
            key = str(ref)
            candidate = TraversalResult(
                ref=ref,
                depth=int(row["depth"]),
                confidence=float(row["confidence"]),
                path=list(row["rel_path"]),
            )
            if key not in best or candidate.confidence > best[key].confidence:
                best[key] = candidate
        return sorted(best.values(), key=lambda r: (-r.confidence, r.depth, str(r.ref)))

    def clear(self) -> None:
        self._run("MATCH (n:Entity) DETACH DELETE n")
