"""POST /api/projects/{project_id}/evaluations -- trigger a real evaluation
run. `project_id` names the URL scope but is not itself passed to
`run_evaluations()` -- `EvaluationRequest.subject_ref` is what the request
body actually scores; the path segment exists for symmetry with the other
project-scoped write endpoints.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from domain.metamodel.registry import MetamodelRegistry
from project_graph.service import ProjectGraphService

from orchestrator.evaluate import run_evaluations
from orchestrator.result import EvaluationOutcome

from webui.api.schemas import EvaluationRunRequest
from webui.api.translate import build_evaluation_request
from webui.context import get_registry, get_service

router = APIRouter(prefix="/api")


@router.post("/projects/{project_id}/evaluations")
async def trigger_evaluation(
    project_id: str,
    body: EvaluationRunRequest,
    service: Annotated[ProjectGraphService, Depends(get_service)],
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
) -> EvaluationOutcome:
    request = build_evaluation_request(body, registry)
    [outcome] = run_evaluations(service, registry, [request])
    return outcome
