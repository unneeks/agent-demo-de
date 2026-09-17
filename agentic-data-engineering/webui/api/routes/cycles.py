"""POST /api/projects/{project_id}/cycles -- trigger orchestrator.cycle.
run_cycle(). Reuses the exact same `webui.api.translate` builders
`evaluations.py`/`gates.py`/`agent_runs.py` each call once -- no
duplicated translation logic.

`observe` is always `None`. `ObserveRequest.repository_root` is a
server-local filesystem path; with zero authentication in front of a
read-write API, accepting an arbitrary path from a remote caller is a real
access-boundary risk, not just a missing feature. Discovery stays
`scripts/`-driven only -- `CycleReport.discovery` is always `None` through
this API. See docs/api-gateway.md's "what this is not."

One documented subtlety: a translation failure inside a list item (e.g. an
unknown `agent_key` in `agent_run_requests`) raises *before* `run_cycle()`
is entered, so it 4xxs the whole request rather than appearing in
`CycleReport.failed` -- a malformed request is rejected outright; a step
that ran and failed is what `on_error="collect"` softly records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import MetamodelRegistry
from persistence.ports import MetadataRepository
from project_graph.service import ProjectGraphService

from orchestrator.cycle import run_cycle
from orchestrator.result import CycleReport

from webui.api.schemas import CycleRunRequest
from webui.api.translate import build_agent_run_request, build_evaluation_request, build_gate_request
from webui.context import get_agent_fixtures_dir, get_metadata, get_registry, get_service
from webui.errors import UnknownDeliveryModelError

router = APIRouter(prefix="/api")


@router.post("/projects/{project_id}/cycles")
async def trigger_cycle(
    project_id: str,
    body: CycleRunRequest,
    service: Annotated[ProjectGraphService, Depends(get_service)],
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    agent_fixtures_dir: Annotated[Path | None, Depends(get_agent_fixtures_dir)],
) -> CycleReport:
    delivery_model = registry.delivery_model(body.delivery_model_key)
    if delivery_model is None:
        raise UnknownDeliveryModelError(body.delivery_model_key)

    project_ref = EntityRef(type=EntityType.PROJECT, id=project_id)

    return run_cycle(
        service,
        registry,
        delivery_model,
        project_ref,
        metadata,
        observe=None,
        change=body.change,
        change_seeds=body.change_seeds,
        max_depth=body.max_depth,
        min_confidence=body.min_confidence,
        agent_run_requests=[
            build_agent_run_request(r, registry, agent_fixtures_dir) for r in body.agent_run_requests
        ],
        evaluation_requests=[build_evaluation_request(r, registry) for r in body.evaluation_requests],
        gates=[build_gate_request(g.gate_key, g) for g in body.gates],
        on_error=body.on_error,
    )
