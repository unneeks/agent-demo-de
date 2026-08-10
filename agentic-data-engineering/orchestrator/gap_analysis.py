"""CAPABILITY GAP ANALYSIS: the I/O layer around `engines/gap_analysis/`.

Fetches real project data (`Pipeline`/`Test`/`Evaluation`), calls the pure
`inference.py`/`chain.py`/`analysis.py` functions with it, and persists the
result -- mirroring `orchestrator/gate.py`'s own `metadata.list(...)`
fetch-and-filter idiom exactly (`_stored_evaluations`/
`_requirement_refs_for_project`), not `webui/graph_discovery.py`'s
traversal: every fact this step needs is reachable by filtering
`MetadataRepository.list()` on `project_ref`/`subject_ref`, so no new graph
dependency is warranted.

Maturity inference is `INFERRED` provenance with a fixed confidence --
`capabilities.yaml`'s own comment says as much: "anything derived from
[detection_hints] is recorded as INFERRED with a confidence." The gap
diff itself (`analyze_capability_gaps`) is `OBSERVED`: comparing two
already-known numbers is transcription, not inference.

Staffing recommendations are advisory only -- no `IMPLEMENTED_BY` write.
A capability gap is a standing assessment, not a specific piece of
triggered work the way a task obligation is; recommending a role is not
the same speech act as staffing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.entities.shared.capability import Capability, CapabilityGap, DeliveryCapability
from domain.metamodel.entities.technical import Pipeline, Test
from domain.metamodel.enums import EntityType, ProvenanceState
from domain.metamodel.registry import LoadedDeliveryModel, MetamodelRegistry
from domain.metamodel.relationships import relationship
from engines.composition import RoleResolution, resolve_role
from engines.gap_analysis import (
    analyze_capability_gaps,
    infer_delivery_maturity,
    infer_technical_maturity,
    tasks_governed_by_delivery_capability,
)
from persistence.ports import MetadataRepository
from project_graph.service import ProjectGraphService

_DISCOVERED_BY = "gap-analysis@0.1.0"
#: A fixed calibration constant, not caller-supplied business data --
#: maturity inference is always a coarse proxy, never presented as more
#: certain than this regardless of how much evidence fed it.
_INFERENCE_CONFIDENCE = 0.6


@dataclass(frozen=True)
class GapAnalysisRequest:
    #: Capability or delivery-capability key -> the maturity level the
    #: project should reach. Never defaulted -- no canonical "desired
    #: maturity" exists anywhere in the registry (mirrors ADR-0019's
    #: ContextPolicy precedent).
    desired_maturity: dict[str, int]


@dataclass(frozen=True)
class GapStaffingRecommendation:
    """Advisory only -- see module docstring."""

    capability_key: str
    role_key: str
    resolution: RoleResolution


@dataclass(frozen=True)
class GapAnalysisOutcome:
    gaps: list[CapabilityGap] = field(default_factory=list)
    recommendations: list[GapStaffingRecommendation] = field(default_factory=list)


def _project_pipelines(metadata: MetadataRepository, project_ref: EntityRef) -> list[Pipeline]:
    all_pipelines = (Pipeline.model_validate(stored.payload) for stored in metadata.list(EntityType.PIPELINE))
    return [p for p in all_pipelines if p.project_ref.id == project_ref.id]


def _project_tests(metadata: MetadataRepository, project_ref: EntityRef) -> list[Test]:
    all_tests = (Test.model_validate(stored.payload) for stored in metadata.list(EntityType.TEST))
    return [t for t in all_tests if t.project_ref.id == project_ref.id]


def _stored_evaluations(metadata: MetadataRepository) -> list[Evaluation]:
    return [Evaluation.model_validate(stored.payload) for stored in metadata.list(EntityType.EVALUATION)]


def _governing_contract_keys(
    delivery_capability_key: str, registry: MetamodelRegistry, delivery_model: LoadedDeliveryModel
) -> list[str]:
    task_keys = tasks_governed_by_delivery_capability(delivery_capability_key, registry, delivery_model)
    keys: list[str] = []
    seen: set[str] = set()
    for task_key in task_keys:
        contract = delivery_model.contract_for(task_key)
        if contract is not None and contract.contract_key not in seen:
            seen.add(contract.contract_key)
            keys.append(contract.contract_key)
    return keys


def analyze_project_capability_gaps(
    service: ProjectGraphService,
    registry: MetamodelRegistry,
    delivery_model: LoadedDeliveryModel,
    metadata: MetadataRepository,
    project_ref: EntityRef,
    request: GapAnalysisRequest,
) -> GapAnalysisOutcome:
    """Infer maturity for every registry-known capability named in
    `request.desired_maturity`, diff against it, and persist the result.

    A `desired_maturity` key that names neither a `registry.capabilities`
    nor a `registry.delivery_capabilities` entry is silently skipped --
    this step infers maturity for *already-cataloged* capabilities, it
    never discovers a new one.
    """
    pipelines = _project_pipelines(metadata, project_ref)
    tests = _project_tests(metadata, project_ref)
    evaluations = _stored_evaluations(metadata)

    capabilities: list[Capability] = []
    for capability_key, spec in registry.capabilities.items():
        if capability_key not in request.desired_maturity:
            continue
        maturity = infer_technical_maturity(spec.detection_hints, pipelines, tests)
        capability = Capability(
            id=f"{project_ref.id}:{capability_key}",
            name=spec.name,
            entity_type=EntityType.CAPABILITY,
            project_ref=project_ref,
            capability_key=capability_key,
            maturity=maturity,
            provenance=ProvenanceState.INFERRED,
            confidence=_INFERENCE_CONFIDENCE,
            discovered_by=_DISCOVERED_BY,
        )
        service.ingest_entity(capability)
        capabilities.append(capability)

    delivery_capabilities: list[DeliveryCapability] = []
    for delivery_capability_key, spec in registry.delivery_capabilities.items():
        if delivery_capability_key not in request.desired_maturity:
            continue
        contract_keys = _governing_contract_keys(delivery_capability_key, registry, delivery_model)
        maturity = infer_delivery_maturity(contract_keys, evaluations)
        delivery_capability = DeliveryCapability(
            id=f"{project_ref.id}:{delivery_capability_key}",
            name=spec.name,
            entity_type=EntityType.DELIVERY_CAPABILITY,
            project_ref=project_ref,
            delivery_capability_key=delivery_capability_key,
            maturity=maturity,
            realized_by_role_keys=list(spec.realized_by_roles),
            provenance=ProvenanceState.INFERRED,
            confidence=_INFERENCE_CONFIDENCE,
            discovered_by=_DISCOVERED_BY,
        )
        service.ingest_entity(delivery_capability)
        delivery_capabilities.append(delivery_capability)

    gaps = analyze_capability_gaps(
        project_ref, capabilities, delivery_capabilities, request.desired_maturity, registry
    )

    recommendations: list[GapStaffingRecommendation] = []
    for gap in gaps:
        service.ingest_entity(gap)
        # Unlike staffing.py's IMPLEMENTED_BY (which has
        # StaffingOutcome.implemented_by_written to report a failed write
        # without aborting other obligations), a CapabilityGap has no
        # per-gap success flag -- so a HAS_GAP write failure is left to
        # propagate to run_cycle's on_error handling rather than swallowed
        # silently here.
        service.ingest_relationship(
            relationship("HAS_GAP", project_ref, gap.ref(), discovered_by=_DISCOVERED_BY), registry
        )

        for role_key in gap.recommended_role_keys:
            role = registry.role(role_key)
            if role is None:
                continue
            resolution = resolve_role(role, registry.agents.values())
            recommendations.append(
                GapStaffingRecommendation(
                    capability_key=gap.capability_key, role_key=role_key, resolution=resolution
                )
            )

    return GapAnalysisOutcome(gaps=gaps, recommendations=recommendations)


__all__ = [
    "GapAnalysisOutcome",
    "GapAnalysisRequest",
    "GapStaffingRecommendation",
    "analyze_project_capability_gaps",
]
