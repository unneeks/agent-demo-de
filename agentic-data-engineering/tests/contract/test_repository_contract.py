"""One contract, every adapter.

Parameterized across the in-memory adapters and the real Neo4j / PostgreSQL
ones. That is the point: the in-memory implementation is only a legitimate
stand-in for the unit suite if it is held to exactly the same behaviour as the
real thing.

Run with no infrastructure and the real-store variants skip. Run
``docker compose up -d`` first and the identical assertions execute against
Neo4j and PostgreSQL.
"""

from __future__ import annotations

import pytest

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.shared.work import Decision
from domain.metamodel.enums import AgentLifecycle, EntityType, ProvenanceState
from domain.metamodel.relationships import relationship
from tests.conftest import make_agent, make_pipeline, ref


class TestMetadataRepositoryContract:
    """Entity state: write, read, version, supersede, delete."""

    def test_upsert_then_get(self, metadata_repo) -> None:
        metadata_repo.upsert(make_agent("regression-agent", "regression-engineer", version="1.0.0"))
        stored = metadata_repo.get(EntityType.AGENT, "regression-agent")
        assert stored is not None and stored.version == "1.0.0"
        assert stored.payload["role_key"] == "regression-engineer"

    def test_missing_entity_returns_none(self, metadata_repo) -> None:
        assert metadata_repo.get(EntityType.AGENT, "does-not-exist") is None

    def test_new_version_supersedes_the_old(self, metadata_repo) -> None:
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="1.0.0"))
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="2.0.0"))
        assert metadata_repo.get(EntityType.AGENT, "a").version == "2.0.0"
        assert metadata_repo.versions(EntityType.AGENT, "a") == ["1.0.0", "2.0.0"]

    def test_superseded_versions_remain_retrievable(self, metadata_repo) -> None:
        """Replaying an old decision needs the exact version that ran."""
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="1.0.0"))
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="2.0.0"))
        old = metadata_repo.get(EntityType.AGENT, "a", version="1.0.0")
        assert old is not None and not old.is_current

    def test_only_one_version_is_current(self, metadata_repo) -> None:
        for version in ("1.0.0", "2.0.0", "3.0.0"):
            metadata_repo.upsert(make_agent("a", "regression-engineer", version=version))
        current = [e for e in metadata_repo.list(EntityType.AGENT) if e.is_current]
        assert len(current) == 1 and current[0].version == "3.0.0"

    def test_rewriting_the_same_version_is_idempotent(self, metadata_repo) -> None:
        agent = make_agent("a", "regression-engineer", version="1.0.0")
        first = metadata_repo.upsert(agent)
        second = metadata_repo.upsert(agent)
        assert first.content_hash == second.content_hash
        assert metadata_repo.versions(EntityType.AGENT, "a") == ["1.0.0"]

    def test_content_hash_tracks_content(self, metadata_repo) -> None:
        original = metadata_repo.upsert(make_agent("a", "regression-engineer", version="1.0.0"))
        changed = metadata_repo.upsert(
            make_agent("a", "regression-engineer", version="1.0.0", status=AgentLifecycle.CANDIDATE)
        )
        assert original.content_hash != changed.content_hash

    def test_list_is_scoped_by_type(self, metadata_repo) -> None:
        metadata_repo.upsert(make_agent("a", "regression-engineer"))
        metadata_repo.upsert(make_pipeline("stg_customers"))
        assert [e.entity_id for e in metadata_repo.list(EntityType.AGENT)] == ["a"]
        assert [e.entity_id for e in metadata_repo.list(EntityType.PIPELINE)] == ["stg_customers"]

    def test_list_can_include_superseded_versions(self, metadata_repo) -> None:
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="1.0.0"))
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="2.0.0"))
        assert len(metadata_repo.list(EntityType.AGENT, current_only=False)) == 2

    def test_delete_removes_every_version(self, metadata_repo) -> None:
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="1.0.0"))
        metadata_repo.upsert(make_agent("a", "regression-engineer", version="2.0.0"))
        assert metadata_repo.delete(EntityType.AGENT, "a") is True
        assert metadata_repo.get(EntityType.AGENT, "a") is None

    def test_deleting_a_missing_entity_reports_false(self, metadata_repo) -> None:
        assert metadata_repo.delete(EntityType.AGENT, "ghost") is False

    def test_delivery_entities_round_trip_too(self, metadata_repo, delivery_model) -> None:
        """Both twins share one store; nothing is technical-only."""
        task = delivery_model.tasks["task.logical-data-model"]
        metadata_repo.upsert(task)
        stored = metadata_repo.get(EntityType.DELIVERY_TASK, task.id)
        assert stored is not None
        assert stored.payload["task_key"] == "task.logical-data-model"
        assert stored.payload["twin"] == "DELIVERY"


class TestMetadataRelationshipLogContract:
    """The durable relationship log ADR-0001 promises: the graph plane's other
    half. Added in Phase 2 -- Postgres always had it; the in-memory adapter did
    not until ProjectGraphService.rebuild_graph needed a real reference
    implementation to test against."""

    def test_upsert_then_list(self, metadata_repo) -> None:
        rel = relationship(
            "DEPENDS_ON",
            ref(EntityType.PIPELINE, "stg_customers"),
            ref(EntityType.DATA_ASSET, "raw.customers"),
            discovered_by="dbt@1.0.0",
        )
        metadata_repo.upsert_relationship(rel)
        stored = metadata_repo.all_relationships()
        assert [r.id for r in stored] == [rel.id]

    def test_rewriting_the_same_edge_updates_it(self, metadata_repo) -> None:
        source = ref(EntityType.PIPELINE, "p")
        target = ref(EntityType.DATA_ASSET, "a")
        metadata_repo.upsert_relationship(
            relationship(
                "DEPENDS_ON", source, target,
                provenance=ProvenanceState.INFERRED, confidence=0.4,
            )
        )
        metadata_repo.upsert_relationship(
            relationship(
                "DEPENDS_ON", source, target,
                provenance=ProvenanceState.INFERRED, confidence=0.9,
            )
        )
        stored = metadata_repo.all_relationships()
        assert len(stored) == 1
        assert stored[0].confidence == pytest.approx(0.9)

    def test_empty_log_returns_empty_list(self, metadata_repo) -> None:
        assert metadata_repo.all_relationships() == []


class TestAuditLedgerContract:
    """The ledger only grows, and tampering is detectable."""

    @staticmethod
    def _decision(decision_id: str, summary: str = "Recommend a regression run.") -> Decision:
        return Decision(
            id=decision_id,
            name=decision_id,
            entity_type=EntityType.DECISION,
            summary=summary,
            outcome="recommend",
        )

    def test_entries_append_in_order(self, metadata_repo) -> None:
        for n in range(3):
            metadata_repo.append_audit(self._decision(f"dec-{n}"))
        entries = metadata_repo.audit_entries()
        assert [e.decision_id for e in entries] == ["dec-0", "dec-1", "dec-2"]
        assert [e.sequence for e in entries] == [0, 1, 2]

    def test_first_entry_has_no_predecessor(self, metadata_repo) -> None:
        metadata_repo.append_audit(self._decision("dec-0"))
        assert metadata_repo.audit_entries()[0].previous_hash is None

    def test_entries_chain_to_their_predecessor(self, metadata_repo) -> None:
        metadata_repo.append_audit(self._decision("dec-0"))
        metadata_repo.append_audit(self._decision("dec-1"))
        entries = metadata_repo.audit_entries()
        assert entries[1].previous_hash == entries[0].entry_hash

    def test_chain_verifies(self, metadata_repo) -> None:
        for n in range(5):
            metadata_repo.append_audit(self._decision(f"dec-{n}", summary=f"Decision {n}."))
        assert metadata_repo.verify_audit_chain() is True

    def test_empty_ledger_verifies(self, metadata_repo) -> None:
        assert metadata_repo.verify_audit_chain() is True

    def test_distinct_decisions_hash_differently(self, metadata_repo) -> None:
        first = metadata_repo.append_audit(self._decision("dec-0", summary="First."))
        second = metadata_repo.append_audit(self._decision("dec-1", summary="Second."))
        assert first.entry_hash != second.entry_hash


class TestGraphRepositoryContract:
    """Relationships, neighbours and confidence-weighted traversal."""

    def test_upsert_and_read_back_an_edge(self, graph_repo) -> None:
        source = ref(EntityType.PIPELINE, "stg_customers")
        target = ref(EntityType.DATA_ASSET, "raw.customers")
        graph_repo.upsert_relationship(
            relationship("DEPENDS_ON", source, target, discovered_by="dbt@1.0.0")
        )
        edge = graph_repo.get_relationship(source, "DEPENDS_ON", target)
        assert edge is not None
        assert edge.provenance is ProvenanceState.OBSERVED
        assert edge.discovered_by == "dbt@1.0.0"

    def test_missing_edge_returns_none(self, graph_repo) -> None:
        assert (
            graph_repo.get_relationship(
                ref(EntityType.PIPELINE, "a"), "DEPENDS_ON", ref(EntityType.DATA_ASSET, "b")
            )
            is None
        )

    def test_edges_are_identified_by_endpoints_and_type(self, graph_repo) -> None:
        source = ref(EntityType.PIPELINE, "p")
        target = ref(EntityType.DATA_ASSET, "a")
        for confidence in (0.5, 0.9):
            graph_repo.upsert_relationship(
                relationship(
                    "DEPENDS_ON",
                    source,
                    target,
                    provenance=ProvenanceState.INFERRED,
                    confidence=confidence,
                )
            )
        edges = graph_repo.relationships(source=source, type_="DEPENDS_ON")
        assert len(edges) == 1 and edges[0].confidence == 0.9

    def test_inferred_edges_keep_their_confidence(self, graph_repo) -> None:
        source = ref(EntityType.DELIVERY_ARTIFACT, "logical-model-v3")
        target = ref(EntityType.PIPELINE, "mart_customer_360")
        graph_repo.upsert_relationship(
            relationship(
                "DESCRIBES",
                source,
                target,
                provenance=ProvenanceState.INFERRED,
                confidence=0.62,
                discovered_by="doc-extractor@0.1.0",
            )
        )
        edge = graph_repo.get_relationship(source, "DESCRIBES", target)
        assert edge is not None
        assert edge.confidence == pytest.approx(0.62)
        assert not edge.is_factual

    def test_document_provenance_survives_a_round_trip(self, graph_repo) -> None:
        """A gate rule read from a PDF must still name the PDF after storage."""
        from domain.metamodel.enums import ExtractionMethod

        source = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
        target = ref(EntityType.PIPELINE, "stg_customers")
        graph_repo.upsert_relationship(
            relationship(
                "GOVERNS",
                source,
                target,
                provenance=ProvenanceState.INFERRED,
                confidence=0.8,
                extraction_method=ExtractionMethod.SEMANTIC_EXTRACTION,
                source_document="DeliveryHandbook.pdf",
                source_section="6.3",
            )
        )
        edge = graph_repo.get_relationship(source, "GOVERNS", target)
        assert edge is not None
        assert edge.citation == "DeliveryHandbook.pdf#6.3"
        assert edge.extraction_method is ExtractionMethod.SEMANTIC_EXTRACTION

    def test_neighbors_respect_direction(self, graph_repo) -> None:
        pipeline = ref(EntityType.PIPELINE, "stg_customers")
        upstream = ref(EntityType.DATA_ASSET, "raw.customers")
        graph_repo.upsert_relationship(relationship("DEPENDS_ON", pipeline, upstream))
        assert graph_repo.neighbors(pipeline, direction="outgoing") == [upstream]
        assert graph_repo.neighbors(pipeline, direction="incoming") == []
        assert graph_repo.neighbors(upstream, direction="incoming") == [pipeline]

    def test_neighbors_filter_by_type(self, graph_repo) -> None:
        pipeline = ref(EntityType.PIPELINE, "p")
        asset = ref(EntityType.DATA_ASSET, "a")
        task = ref(EntityType.DELIVERY_TASK, "t")
        graph_repo.upsert_relationship(relationship("DEPENDS_ON", pipeline, asset))
        graph_repo.upsert_relationship(relationship("GOVERNS", task, pipeline))
        assert graph_repo.neighbors(pipeline, type_="DEPENDS_ON", direction="outgoing") == [asset]
        assert graph_repo.neighbors(pipeline, type_="GOVERNS", direction="incoming") == [task]

    def test_neighbors_return_unversioned_identities(self, graph_repo) -> None:
        """Nodes are keyed by type and id; versions live in the metadata plane."""
        role = ref(EntityType.ENGINEERING_ROLE, "regression-engineer")
        pinned = EntityRef(type=EntityType.AGENT, id="regression-agent", version="1.0.0")
        graph_repo.upsert_relationship(relationship("IMPLEMENTED_BY", role, pinned))
        assert graph_repo.neighbors(role, type_="IMPLEMENTED_BY") == [
            ref(EntityType.AGENT, "regression-agent")
        ]

    def test_rejects_an_unknown_direction(self, graph_repo) -> None:
        with pytest.raises(ValueError, match="outgoing, incoming or both"):
            graph_repo.neighbors(ref(EntityType.PIPELINE, "p"), direction="sideways")

    def test_clear_empties_the_graph(self, graph_repo) -> None:
        graph_repo.upsert_relationship(
            relationship(
                "DEPENDS_ON", ref(EntityType.PIPELINE, "p"), ref(EntityType.DATA_ASSET, "a")
            )
        )
        graph_repo.clear()
        assert graph_repo.relationships() == []


class TestTraversalContract:
    """Confidence-weighted traversal -- the primitive both engines build on."""

    @staticmethod
    def _chain(graph_repo) -> None:
        """raw.customers <- stg_customers <- mart_customer_360, plus a test."""
        graph_repo.upsert_relationship(
            relationship(
                "DEPENDS_ON",
                ref(EntityType.PIPELINE, "stg_customers"),
                ref(EntityType.DATA_ASSET, "raw.customers"),
            )
        )
        graph_repo.upsert_relationship(
            relationship(
                "DEPENDS_ON",
                ref(EntityType.PIPELINE, "mart_customer_360"),
                ref(EntityType.PIPELINE, "stg_customers"),
            )
        )
        graph_repo.upsert_relationship(
            relationship(
                "COVERS",
                ref(EntityType.TEST, "test_customer_360"),
                ref(EntityType.PIPELINE, "mart_customer_360"),
            )
        )

    def test_finds_the_blast_radius(self, graph_repo) -> None:
        self._chain(graph_repo)
        reached = {
            r.ref.id
            for r in graph_repo.traverse(
                ref(EntityType.DATA_ASSET, "raw.customers"), max_depth=5, direction="incoming"
            )
        }
        assert reached == {"stg_customers", "mart_customer_360", "test_customer_360"}

    def test_depth_limits_the_walk(self, graph_repo) -> None:
        self._chain(graph_repo)
        reached = {
            r.ref.id
            for r in graph_repo.traverse(
                ref(EntityType.DATA_ASSET, "raw.customers"), max_depth=1, direction="incoming"
            )
        }
        assert reached == {"stg_customers"}

    def test_relationship_type_filter_applies(self, graph_repo) -> None:
        self._chain(graph_repo)
        reached = {
            r.ref.id
            for r in graph_repo.traverse(
                ref(EntityType.DATA_ASSET, "raw.customers"),
                relationship_types=["DEPENDS_ON"],
                max_depth=5,
                direction="incoming",
            )
        }
        assert reached == {"stg_customers", "mart_customer_360"}

    def test_confidence_degrades_along_inferred_hops(self, graph_repo) -> None:
        """Two inferred hops at 0.8 must read as 0.64, not as certainty."""
        for source, target in (("b", "a"), ("c", "b")):
            graph_repo.upsert_relationship(
                relationship(
                    "DEPENDS_ON",
                    ref(EntityType.PIPELINE, source),
                    ref(EntityType.PIPELINE if target != "a" else EntityType.DATA_ASSET, target),
                    provenance=ProvenanceState.INFERRED,
                    confidence=0.8,
                )
            )
        results = {
            r.ref.id: r.confidence
            for r in graph_repo.traverse(
                ref(EntityType.DATA_ASSET, "a"), max_depth=5, direction="incoming"
            )
        }
        assert results["b"] == pytest.approx(0.8)
        assert results["c"] == pytest.approx(0.64)

    def test_observed_hops_stay_certain(self, graph_repo) -> None:
        self._chain(graph_repo)
        results = graph_repo.traverse(
            ref(EntityType.DATA_ASSET, "raw.customers"), max_depth=5, direction="incoming"
        )
        assert all(r.confidence == pytest.approx(1.0) for r in results)

    def test_min_confidence_prunes_speculation(self, graph_repo) -> None:
        graph_repo.upsert_relationship(
            relationship(
                "DEPENDS_ON",
                ref(EntityType.PIPELINE, "b"),
                ref(EntityType.DATA_ASSET, "a"),
                provenance=ProvenanceState.INFERRED,
                confidence=0.3,
            )
        )
        assert (
            graph_repo.traverse(
                ref(EntityType.DATA_ASSET, "a"), min_confidence=0.5, direction="incoming"
            )
            == []
        )

    def test_results_are_ordered_by_confidence(self, graph_repo) -> None:
        for node, confidence in (("high", 0.9), ("low", 0.2), ("mid", 0.5)):
            graph_repo.upsert_relationship(
                relationship(
                    "DEPENDS_ON",
                    ref(EntityType.PIPELINE, node),
                    ref(EntityType.DATA_ASSET, "a"),
                    provenance=ProvenanceState.INFERRED,
                    confidence=confidence,
                )
            )
        results = graph_repo.traverse(ref(EntityType.DATA_ASSET, "a"), direction="incoming")
        assert [r.ref.id for r in results] == ["high", "mid", "low"]

    def test_traversal_records_the_path_taken(self, graph_repo) -> None:
        """An impact claim has to be able to show its working."""
        self._chain(graph_repo)
        results = {
            r.ref.id: r.path
            for r in graph_repo.traverse(
                ref(EntityType.DATA_ASSET, "raw.customers"), max_depth=5, direction="incoming"
            )
        }
        assert results["test_customer_360"] == ["DEPENDS_ON", "DEPENDS_ON", "COVERS"]

    def test_cross_twin_traversal_works(self, graph_repo) -> None:
        """The join must be walkable, or the two twins are separate models."""
        graph_repo.upsert_relationship(
            relationship(
                "GOVERNS",
                ref(EntityType.DELIVERY_TASK, "task.logical-data-model"),
                ref(EntityType.PIPELINE, "stg_customers"),
            )
        )
        reached = graph_repo.traverse(
            ref(EntityType.PIPELINE, "stg_customers"), direction="incoming"
        )
        assert [r.ref.type for r in reached] == [EntityType.DELIVERY_TASK]

    def test_cycles_terminate(self, graph_repo) -> None:
        for source, target in (("a", "b"), ("b", "a")):
            graph_repo.upsert_relationship(
                relationship(
                    "DEPENDS_ON", ref(EntityType.PIPELINE, source), ref(EntityType.PIPELINE, target)
                )
            )
        results = graph_repo.traverse(ref(EntityType.PIPELINE, "a"), max_depth=10)
        assert [r.ref.id for r in results] == ["b"]

    def test_isolated_node_has_no_blast_radius(self, graph_repo) -> None:
        graph_repo.upsert_node(ref(EntityType.DATA_ASSET, "orphan"))
        assert graph_repo.traverse(ref(EntityType.DATA_ASSET, "orphan")) == []


class TestCrossPlaneConsistency:
    """The two planes describe the same world."""

    def test_graph_is_rebuildable_from_stored_relationships(self, memory_graph) -> None:
        """Neo4j is a projection; dropping it must lose nothing durable."""
        from persistence.memory import InMemoryGraphRepository

        edges = [
            relationship(
                "DEPENDS_ON",
                ref(EntityType.PIPELINE, "stg_customers"),
                ref(EntityType.DATA_ASSET, "raw.customers"),
            ),
            relationship(
                "GOVERNS",
                ref(EntityType.DELIVERY_TASK, "task.logical-data-model"),
                ref(EntityType.PIPELINE, "stg_customers"),
            ),
        ]
        for edge in edges:
            memory_graph.upsert_relationship(edge)
        original = memory_graph.relationships()

        rebuilt = InMemoryGraphRepository()
        for edge in edges:
            rebuilt.upsert_relationship(edge)
        assert [str(e) for e in rebuilt.relationships()] == [str(e) for e in original]

    def test_both_twins_persist_and_traverse_together(
        self, memory_metadata, memory_graph, delivery_model
    ) -> None:
        pipeline = make_pipeline("stg_customers")
        task = delivery_model.tasks["task.logical-data-model"]
        memory_metadata.upsert(pipeline)
        memory_metadata.upsert(task)
        memory_graph.upsert_relationship(
            relationship("GOVERNS", task.ref(), pipeline.ref(), discovered_by="delivery")
        )

        governing = memory_graph.neighbors(pipeline.ref(), type_="GOVERNS", direction="incoming")
        assert governing == [task.ref()]
        for found in governing:
            assert memory_metadata.get(found.type, found.id) is not None
