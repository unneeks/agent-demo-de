"""`run_cycle` -- the entry point composing GAP ANALYSIS (optional) ->
OBSERVE (optional) -> DETECT CHANGE + IMPACT -> SELECT AGENTS -> EVALUATE ->
APPROVAL GATE over one real project.

Every step calls an existing Phase 1-6 function with real data -- no new
scoring, no new resolution logic, no new gate math. Every write goes through
`ProjectGraphService`, never `persistence.ports` directly, mirroring
`discovery/orchestrate.py`'s discipline exactly. `on_error="collect"` (the
default) records a per-step failure and continues -- a single obligation's
or evaluation's rejected write should not discard every other step's good
work; `"fail_fast"` re-raises immediately instead.

GAP ANALYSIS (`gap_analysis`, ADR-0021) runs independently of `change`/
`observe` -- a standing capability-maturity assessment, not something a
change triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.technical import Change, Project
from domain.metamodel.registry import LoadedDeliveryModel, MetamodelRegistry
from discovery.extraction.client import ExtractionClient
from discovery.orchestrate import discover_project
from persistence.ports import MetadataRepository
from project_graph.errors import IngestionError
from project_graph.service import ProjectGraphService

from agent_runtime.errors import AgentRuntimeError

from orchestrator.agent_step import AgentRunRequest, run_agents
from orchestrator.errors import OrchestratorError
from orchestrator.evaluate import EvaluationRequest, run_evaluations
from orchestrator.gap_analysis import GapAnalysisRequest, analyze_project_capability_gaps
from orchestrator.gate import GateRequest, assess_gate_readiness
from orchestrator.result import CycleFailure, CycleReport
from orchestrator.staffing import select_agents


@dataclass(frozen=True)
class ObserveRequest:
    """Wraps `discover_project`'s own arguments so `run_cycle` can call it as
    step 0. `discover_project` itself calls `service.register_project`."""

    project: Project
    client: ExtractionClient
    repository_root: Path
    repository_id: str | None = None
    on_error: Literal["fail_fast", "collect"] = "collect"


def run_cycle(
    service: ProjectGraphService,
    registry: MetamodelRegistry,
    delivery_model: LoadedDeliveryModel,
    project_ref: EntityRef,
    metadata: MetadataRepository,
    *,
    observe: ObserveRequest | None = None,
    change: Change | None = None,
    change_seeds: list[EntityRef] | None = None,
    max_depth: int = 5,
    min_confidence: float = 0.0,
    agent_run_requests: list[AgentRunRequest] | None = None,
    evaluation_requests: list[EvaluationRequest] | None = None,
    gates: list[GateRequest] | None = None,
    gap_analysis: GapAnalysisRequest | None = None,
    on_error: Literal["fail_fast", "collect"] = "collect",
) -> CycleReport:
    """Every step is independently optional except `project_ref` itself: a
    cycle can be gate-reassessment-only, staffing-only, or the full
    pipeline."""
    failed: list[CycleFailure] = []

    discovery_report = None
    if observe is not None:
        if observe.project.id != project_ref.id:
            raise OrchestratorError(
                f"ObserveRequest.project.id {observe.project.id!r} does not match "
                f"run_cycle's own project_ref.id {project_ref.id!r}"
            )
        discovery_report = discover_project(
            service,
            registry,
            observe.project,
            observe.client,
            repository_root=observe.repository_root,
            repository_id=observe.repository_id,
            on_error=observe.on_error,
        )

    def _record(kind: str, detail: str, source: str) -> None:
        if on_error == "fail_fast":
            raise IngestionError(f"cycle step failed ({kind}): {detail}")
        failed.append(CycleFailure(kind=kind, detail=detail, source=source))

    gap_analysis_outcome = None
    if gap_analysis is not None:
        try:
            gap_analysis_outcome = analyze_project_capability_gaps(
                service, registry, delivery_model, metadata, project_ref, gap_analysis
            )
        except (IngestionError, ValueError) as exc:
            _record("gap_analysis_failed", str(exc), project_ref.id)

    impact = None
    staffing = []
    if change is not None:
        try:
            impact = service.analyze_change(
                change, delivery_model, seeds=change_seeds, max_depth=max_depth, min_confidence=min_confidence
            )
        except (IngestionError, ValueError) as exc:
            _record("impact_analysis_failed", str(exc), change.id)
        else:
            staffing = select_agents(
                service, registry, delivery_model, project_ref, impact.delivery.all_obligations()
            )

    agent_runs = []
    for request in agent_run_requests or []:
        try:
            [outcome] = run_agents(registry, [request])
        except (AgentRuntimeError, KeyError) as exc:
            _record("agent_run_failed", str(exc), request.agent_key)
            continue
        agent_runs.append(outcome)

    evaluations = []
    for request in evaluation_requests or []:
        try:
            [outcome] = run_evaluations(service, registry, [request])
        except (IngestionError, ValueError) as exc:
            _record("evaluation_failed", str(exc), f"{request.suite_key}:{request.subject_ref}")
            continue
        evaluations.append(outcome)

    gate_readiness = {}
    for gate_request in gates or []:
        try:
            gate_readiness[gate_request.gate_key] = assess_gate_readiness(
                service, metadata, delivery_model, project_ref, gate_request
            )
        except (IngestionError, ValueError) as exc:
            _record("gate_assessment_failed", str(exc), gate_request.gate_key)

    return CycleReport(
        project_ref=project_ref,
        discovery=discovery_report,
        impact=impact,
        staffing=staffing,
        agent_runs=agent_runs,
        evaluations=evaluations,
        gate_readiness=gate_readiness,
        gap_analysis=gap_analysis_outcome,
        failed=failed,
    )
