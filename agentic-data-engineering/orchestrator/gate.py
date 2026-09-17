"""APPROVAL GATE: assembling a `GateState` with the two fields that now have
real assemblers, and calling the untouched `assess_gate` through the facade.

`passed_evaluations` (Phase 5's `passed_evaluation_keys`) and `traceability`
(this phase's `ProjectGraphService.assess_traceability`) are sourced from
actual persisted graph/metadata state, never a literal. The other four
`GateState` fields -- `present_artifact_kinds`, `checklist_outcomes`,
`satisfied_evidence`, `approvals` -- have no real assembler anywhere in this
codebase and stay exactly as caller-supplied on `GateRequest`, named
explicitly here rather than silently absent. See `docs/orchestrator.md`'s
"what this is not."
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.entities.shared.capability import Requirement
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import LoadedDeliveryModel
from engines.evaluation import passed_evaluation_keys
from engines.gates import ChecklistOutcome, GateReadiness, GateState
from persistence.ports import MetadataRepository
from project_graph.service import ProjectGraphService

from orchestrator.errors import UnknownGateError


@dataclass(frozen=True)
class GateRequest:
    gate_key: str
    present_artifact_kinds: set[str] = field(default_factory=set)
    checklist_outcomes: dict[str, ChecklistOutcome] = field(default_factory=dict)
    satisfied_evidence: set[str] = field(default_factory=set)
    approvals: set[str] = field(default_factory=set)
    #: Optional filter -- only evaluations of this subject count toward
    #: passed_evaluations. Omit to consider every stored evaluation.
    evaluation_subject_ref: EntityRef | None = None


def _stored_evaluations(metadata: MetadataRepository) -> list[Evaluation]:
    return [Evaluation.model_validate(stored.payload) for stored in metadata.list(EntityType.EVALUATION)]


def _requirement_refs_for_project(
    metadata: MetadataRepository, project_ref: EntityRef
) -> list[EntityRef]:
    requirements = [
        Requirement.model_validate(stored.payload) for stored in metadata.list(EntityType.REQUIREMENT)
    ]
    return [
        EntityRef(type=EntityType.REQUIREMENT, id=r.id)
        for r in requirements
        if r.project_ref.id == project_ref.id
    ]


def assemble_gate_state(
    service: ProjectGraphService,
    metadata: MetadataRepository,
    project_ref: EntityRef,
    request: GateRequest,
) -> GateState:
    """Real assemblers for `passed_evaluations`/`traceability`; the other
    four fields pass straight through from `request`."""
    evaluations = _stored_evaluations(metadata)
    passed = passed_evaluation_keys(evaluations, subject_ref=request.evaluation_subject_ref)

    requirement_refs = _requirement_refs_for_project(metadata, project_ref)
    traceability = service.assess_traceability(requirement_refs)

    return GateState(
        present_artifact_kinds=request.present_artifact_kinds,
        checklist_outcomes=request.checklist_outcomes,
        passed_evaluations=passed,
        satisfied_evidence=request.satisfied_evidence,
        approvals=request.approvals,
        traceability=traceability,
    )


def assess_gate_readiness(
    service: ProjectGraphService,
    metadata: MetadataRepository,
    delivery_model: LoadedDeliveryModel,
    project_ref: EntityRef,
    request: GateRequest,
) -> GateReadiness:
    gate = delivery_model.gates.get(request.gate_key)
    if gate is None:
        raise UnknownGateError(request.gate_key)
    state = assemble_gate_state(service, metadata, project_ref, request)
    return service.assess_readiness(gate, state)
