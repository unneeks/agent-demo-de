"""ProjectGraphService -- lifecycle, dual-plane consistency, snapshotting and
the project-scoped query facade.

A thin front door over Phase 1's ports and engines, so these tests prove
composition, not new engine behaviour: a fact ingested through the service is
visible on both planes, a snapshot is restorable and deterministic, and the
facade methods return exactly what calling the engines directly would.
"""

from __future__ import annotations

import pytest

from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import relationship
from engines.gates import GateState, assess_gate
from engines.impact import analyze_impact, trace, traceability_score
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from project_graph import ProjectGraphService
from project_graph.errors import IngestionError, SnapshotError, UnknownProjectError
from project_graph.snapshot import build_snapshot
from tests.conftest import make_change, make_code, make_pipeline, make_project, ref

PROJECT_REF = ref(EntityType.PROJECT, "demo")
SQL_REF = ref(EntityType.CODE_ARTIFACT, "customer_address.sql")
STG_REF = ref(EntityType.PIPELINE, "stg_customers")


@pytest.fixture
def service(metadata: InMemoryMetadataRepository, graph: InMemoryGraphRepository) -> ProjectGraphService:
    return ProjectGraphService(metadata, graph)


def _seed(service: ProjectGraphService, registry) -> None:
    """A project containing one code artifact and one pipeline that depends on it."""
    service.register_project(make_project("demo"))
    service.ingest_entity(make_code("customer_address.sql"))
    service.ingest_entity(make_pipeline("stg_customers"))
    service.ingest_relationship(
        relationship("CONTAINS", PROJECT_REF, SQL_REF, discovered_by="fixture"), registry
    )
    service.ingest_relationship(
        relationship("CONTAINS", PROJECT_REF, STG_REF, discovered_by="fixture"), registry
    )
    service.ingest_relationship(
        relationship("DEPENDS_ON", STG_REF, SQL_REF, discovered_by="fixture"), registry
    )


class TestLifecycle:
    def test_register_project_writes_both_planes(self, service, metadata, graph) -> None:
        stored = service.register_project(make_project("demo"))
        assert stored.entity_id == "demo"
        assert metadata.get(EntityType.PROJECT, "demo") is not None
        assert graph.neighbors(PROJECT_REF, direction="both") == []  # node exists, no edges yet

    def test_ingest_entity_writes_both_planes(self, service, metadata, graph, registry) -> None:
        service.register_project(make_project("demo"))
        service.ingest_entity(make_code("customer_address.sql"))
        assert metadata.get(EntityType.CODE_ARTIFACT, "customer_address.sql") is not None

        service.ingest_relationship(
            relationship("CONTAINS", PROJECT_REF, SQL_REF, discovered_by="fixture"), registry
        )
        assert graph.get_relationship(PROJECT_REF, "CONTAINS", SQL_REF) is not None

    def test_ingest_entity_rejects_an_unregistered_entity_type(self, service) -> None:
        class Bogus:
            entity_type = "NotARealType"
            id = "x"
            name = "x"
            twin = None

        with pytest.raises(IngestionError, match="not registered"):
            service.ingest_entity(Bogus())  # type: ignore[arg-type]

    def test_ingest_relationship_writes_both_planes(self, service, metadata, graph, registry) -> None:
        _seed(service, registry)
        assert metadata.get(EntityType.PIPELINE, "stg_customers") is not None
        assert graph.get_relationship(STG_REF, "DEPENDS_ON", SQL_REF) is not None

    def test_dual_plane_edge_is_independently_traversable(self, service, graph, registry) -> None:
        _seed(service, registry)
        reached = {str(r.ref) for r in graph.traverse(SQL_REF, direction="incoming")}
        assert str(STG_REF) in reached

    def test_registry_validation_is_enforced_and_nothing_is_written(
        self, service, metadata, graph, registry
    ) -> None:
        """DEPENDS_ON does not permit Project -> CodeArtifact; the write must fail
        before touching either plane -- a partial write is worse than no write."""
        service.register_project(make_project("demo"))
        bad = relationship("DEPENDS_ON", PROJECT_REF, SQL_REF, discovered_by="fixture")
        with pytest.raises(IngestionError, match="DEPENDS_ON"):
            service.ingest_relationship(bad, registry)
        assert graph.get_relationship(PROJECT_REF, "DEPENDS_ON", SQL_REF) is None
        assert bad.id not in {r.id for r in metadata.all_relationships()}


class TestRebuild:
    def test_rebuild_reconstructs_the_graph_plane_from_the_durable_log(
        self, service, graph, registry
    ) -> None:
        _seed(service, registry)
        before = sorted(str(r) for r in graph.relationships())

        graph.clear()
        assert graph.relationships() == []

        count = service.rebuild_graph()
        after = sorted(str(r) for r in graph.relationships())
        assert count == 3
        assert after == before


class TestSnapshot:
    def test_snapshot_pins_the_projects_reachable_state(self, service, registry) -> None:
        _seed(service, registry)
        snapshot = service.snapshot(PROJECT_REF, registry)
        pinned_ids = {ref.id for ref in snapshot.entity_refs}
        assert pinned_ids == {"demo", "customer_address.sql", "stg_customers"}
        assert len(snapshot.relationship_ids) == 3

    def test_snapshot_is_persisted_like_any_other_entity(self, service, metadata, registry) -> None:
        _seed(service, registry)
        snapshot = service.snapshot(PROJECT_REF, registry)
        stored = metadata.get(EntityType.PROJECT_SNAPSHOT, snapshot.id)
        assert stored is not None

    def test_restore_reverts_later_mutations(self, service, graph, registry) -> None:
        _seed(service, registry)
        snapshot = service.snapshot(PROJECT_REF, registry)

        extra_ref = ref(EntityType.CODE_ARTIFACT, "extra.sql")
        service.ingest_entity(make_code("extra.sql"))
        service.ingest_relationship(
            relationship("CONTAINS", PROJECT_REF, extra_ref, discovered_by="fixture"), registry
        )
        assert graph.get_relationship(PROJECT_REF, "CONTAINS", extra_ref) is not None

        service.restore_snapshot(snapshot)
        assert graph.get_relationship(PROJECT_REF, "CONTAINS", extra_ref) is None
        assert graph.get_relationship(STG_REF, "DEPENDS_ON", SQL_REF) is not None

    def test_restore_fails_loudly_when_a_pinned_entity_is_gone(self, service, registry) -> None:
        _seed(service, registry)
        snapshot = service.snapshot(PROJECT_REF, registry)
        service._metadata.delete(EntityType.PIPELINE, "stg_customers")
        with pytest.raises(SnapshotError, match="no longer exist"):
            service.restore_snapshot(snapshot)

    def test_restore_never_touches_the_graph_on_a_failed_precheck(
        self, service, graph, registry
    ) -> None:
        _seed(service, registry)
        snapshot = service.snapshot(PROJECT_REF, registry)
        before = sorted(str(r) for r in graph.relationships())
        service._metadata.delete(EntityType.PIPELINE, "stg_customers")
        with pytest.raises(SnapshotError):
            service.restore_snapshot(snapshot)
        assert sorted(str(r) for r in graph.relationships()) == before

    def test_snapshot_hash_is_order_independent(self, registry) -> None:
        """Two builds of identical state, inserted in different orders, hash the same."""
        edges = [
            relationship("CONTAINS", PROJECT_REF, SQL_REF, discovered_by="fixture"),
            relationship("CONTAINS", PROJECT_REF, STG_REF, discovered_by="fixture"),
            relationship("DEPENDS_ON", STG_REF, SQL_REF, discovered_by="fixture"),
        ]

        def build(entity_order, edge_order):
            metadata = InMemoryMetadataRepository()
            graph = InMemoryGraphRepository()
            svc = ProjectGraphService(metadata, graph)
            svc.register_project(make_project("demo"))
            for entity in entity_order:
                svc.ingest_entity(entity)
            for edge in edge_order:
                svc.ingest_relationship(edge, registry)
            return svc.snapshot(PROJECT_REF, registry)

        snap1 = build([make_code("customer_address.sql"), make_pipeline("stg_customers")], edges)
        snap2 = build(
            [make_pipeline("stg_customers"), make_code("customer_address.sql")],
            list(reversed(edges)),
        )
        assert snap1.snapshot_hash == snap2.snapshot_hash

    def test_build_snapshot_is_pure_and_needs_no_repository(self, registry) -> None:
        snapshot = build_snapshot(
            project_ref=ref(EntityType.PROJECT, "demo", version="0.1.0"),
            registry=registry,
            entity_refs=[ref(EntityType.PROJECT, "demo", version="0.1.0")],
            relationship_ids=[],
        )
        assert snapshot.snapshot_hash


class TestQueryFacade:
    def test_analyze_change_matches_calling_the_engine_directly(self, service, graph, registry, delivery_model) -> None:
        _seed(service, registry)
        change = make_change(impacted_refs=[SQL_REF])
        via_service = service.analyze_change(change, delivery_model)
        via_engine = analyze_impact(change, graph, delivery_model)
        assert via_service == via_engine

    def test_trace_requirement_matches_calling_the_engine_directly(self, service, graph, registry) -> None:
        requirement = ref(EntityType.REQUIREMENT, "REQ-1")
        task = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
        graph.upsert_relationship(
            relationship("TRACED_TO", requirement, task, discovered_by="fixture")
        )
        via_service = service.trace_requirement(requirement)
        via_engine = trace(requirement, graph)
        assert via_service == via_engine

    def test_assess_traceability_matches_calling_the_engine_directly(self, service, graph) -> None:
        requirement = ref(EntityType.REQUIREMENT, "REQ-1")
        task = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
        graph.upsert_relationship(
            relationship("TRACED_TO", requirement, task, discovered_by="fixture")
        )
        via_service = service.assess_traceability([requirement])
        via_engine = traceability_score([requirement], graph)
        assert via_service == via_engine

    def test_assess_traceability_of_nothing_is_fully_traceable(self, service) -> None:
        assert service.assess_traceability([]) == 1.0

    def test_assess_readiness_matches_calling_the_engine_directly(self, service, delivery_model) -> None:
        gate = next(iter(delivery_model.gates.values()))
        state = GateState()
        via_service = service.assess_readiness(gate, state)
        via_engine = assess_gate(gate, state)
        # assessed_at is a fresh timestamp on each call; compare everything else.
        assert via_service.model_dump(exclude={"assessed_at"}) == via_engine.model_dump(
            exclude={"assessed_at"}
        )


class TestErrors:
    def test_unknown_project_raises_on_snapshot(self, service, registry) -> None:
        with pytest.raises(UnknownProjectError):
            service.snapshot(ref(EntityType.PROJECT, "ghost"), registry)
