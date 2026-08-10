"""Deterministic resolution of relationship candidates against an entity
index built from one run's extracted output.

Bookkeeping over strings the agent already produced -- no file content is
read here, so every test builds its index and candidates directly.
"""

from __future__ import annotations

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.technical import DataAsset, Pipeline
from domain.metamodel.enums import EntityType, ProvenanceState
from discovery.extraction.parse_response import RelationshipCandidate
from discovery.resolve import build_entity_index, resolve_relationship_candidates

PROJECT_REF = EntityRef(type=EntityType.PROJECT, id="demo")


def _pipeline(pipeline_id: str) -> Pipeline:
    return Pipeline(
        id=pipeline_id,
        name=pipeline_id,
        entity_type=EntityType.PIPELINE,
        pipeline_kind="dbt_model",
        project_ref=PROJECT_REF,
        provenance=ProvenanceState.INFERRED,
        confidence=0.8,
        discovered_by="agent-extraction@0.1.0",
    )


def _asset(asset_id: str) -> DataAsset:
    return DataAsset(
        id=asset_id,
        name=asset_id,
        entity_type=EntityType.DATA_ASSET,
        asset_kind="dataset",
        project_ref=PROJECT_REF,
        provenance=ProvenanceState.INFERRED,
        confidence=0.8,
        discovered_by="agent-extraction@0.1.0",
    )


class TestBuildEntityIndex:
    def test_indexes_by_type_and_id(self) -> None:
        entities = [_pipeline("p1"), _asset("a1")]
        index = build_entity_index(entities)
        assert index[(EntityType.PIPELINE, "p1")] == EntityRef(type=EntityType.PIPELINE, id="p1")
        assert index[(EntityType.DATA_ASSET, "a1")] == EntityRef(type=EntityType.DATA_ASSET, id="a1")


class TestResolveRelationshipCandidates:
    def test_resolves_a_symbolic_technical_candidate(self) -> None:
        index = build_entity_index([_pipeline("p1"), _asset("raw_customers")])
        candidate = RelationshipCandidate(
            type="DEPENDS_ON",
            source_ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
            confidence=0.85,
            target_kind=EntityType.DATA_ASSET,
            target_symbolic_name="raw_customers",
        )
        resolved, skipped = resolve_relationship_candidates([candidate], index)
        assert not skipped
        [rel] = resolved
        assert rel.type == "DEPENDS_ON"
        assert rel.target == EntityRef(type=EntityType.DATA_ASSET, id="raw_customers")
        assert rel.confidence == 0.85

    def test_a_target_kind_mismatch_is_unresolved_not_force_matched(self) -> None:
        """The index has a Pipeline named `raw_customers`, but the agent
        claimed the target is a DataAsset -- must not be force-matched
        against the Pipeline just because the name lines up."""
        index = build_entity_index([_pipeline("raw_customers")])
        candidate = RelationshipCandidate(
            type="DEPENDS_ON",
            source_ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
            confidence=0.85,
            target_kind=EntityType.DATA_ASSET,
            target_symbolic_name="raw_customers",
        )
        resolved, skipped = resolve_relationship_candidates([candidate], index)
        assert resolved == []
        [skip] = skipped
        assert skip.kind == "unresolved_relationship_target"

    def test_a_missing_name_is_unresolved(self) -> None:
        index = build_entity_index([_pipeline("p1")])
        candidate = RelationshipCandidate(
            type="DEPENDS_ON",
            source_ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
            confidence=0.85,
            target_kind=EntityType.DATA_ASSET,
            target_symbolic_name="does_not_exist",
        )
        resolved, skipped = resolve_relationship_candidates([candidate], index)
        assert resolved == []
        assert skipped[0].kind == "unresolved_relationship_target"

    def test_a_pre_resolved_delivery_candidate_passes_through_unchanged(self) -> None:
        """A DESCRIBES candidate already carries a resolved target_ref
        (resolved at parse time against a known-entities index) -- resolve
        must not attempt a second symbolic lookup for it."""
        index: dict = {}  # deliberately empty -- must not be consulted
        candidate = RelationshipCandidate(
            type="DESCRIBES",
            source_ref=EntityRef(type=EntityType.DELIVERY_ARTIFACT, id="readme"),
            confidence=0.75,
            target_ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
        )
        resolved, skipped = resolve_relationship_candidates([candidate], index)
        assert not skipped
        [rel] = resolved
        assert rel.target == EntityRef(type=EntityType.PIPELINE, id="p1")

    def test_resolved_relationship_carries_inferred_provenance(self) -> None:
        index = build_entity_index([_pipeline("p1"), _asset("a1")])
        candidate = RelationshipCandidate(
            type="DEPENDS_ON",
            source_ref=EntityRef(type=EntityType.PIPELINE, id="p1"),
            confidence=0.85,
            target_kind=EntityType.DATA_ASSET,
            target_symbolic_name="a1",
        )
        [rel], _ = resolve_relationship_candidates([candidate], index)
        assert rel.provenance is ProvenanceState.INFERRED
        assert rel.discovered_by == "agent-extraction@0.1.0"
