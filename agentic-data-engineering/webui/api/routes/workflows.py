"""`/api/workflows` -- start and poll a live multi-agent workflow run.

Unlike every other `/api/*` write endpoint (`agent_runs.py`, `cycles.py`,
...), which trigger one synchronous call and return its final result,
starting a workflow run returns *immediately* with the run's id -- the
run itself keeps going on background threads
(`orchestrator.workflow.WorkflowRunner`), and the caller polls
`GET /api/workflows/{run_id}` for progress. Runs live only in
`app.state.workflow_runs` -- in-process, in-memory, gone on a server
restart (see docs/workflow-dashboard.md's "what this is not").
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from domain.metamodel.registry import MetamodelRegistry

from orchestrator.workflow import WorkflowRunner, WorkflowSnapshot, WorkflowTemplate, start_workflow_run

from webui.api.errors import UnknownWorkflowRunError, UnknownWorkflowTemplateError
from webui.api.schemas import WorkflowApproveRequest, WorkflowRunRequest
from webui.api.translate import build_live_backends
from webui.context import get_registry, get_workflow_runs, get_workflow_templates

router = APIRouter(prefix="/api")


@router.post("/workflows")
async def start_workflow(
    body: WorkflowRunRequest,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    templates: Annotated[dict[str, WorkflowTemplate], Depends(get_workflow_templates)],
    runs: Annotated[dict[str, WorkflowRunner], Depends(get_workflow_runs)],
) -> WorkflowSnapshot:
    template = templates.get(body.template_key)
    if template is None:
        raise UnknownWorkflowTemplateError(body.template_key)

    live_backends = build_live_backends(body, template) if body.mode == "live" else None
    runner = start_workflow_run(run_id=None, template=template, registry=registry, mode=body.mode, live_backends=live_backends)
    runs[runner.snapshot().run_id] = runner
    return runner.snapshot()


@router.get("/workflows/{run_id}")
async def get_workflow(
    run_id: str, runs: Annotated[dict[str, WorkflowRunner], Depends(get_workflow_runs)]
) -> WorkflowSnapshot:
    runner = runs.get(run_id)
    if runner is None:
        raise UnknownWorkflowRunError(run_id)
    return runner.snapshot()


@router.post("/workflows/{run_id}/approve")
async def approve_workflow_work_product(
    run_id: str,
    body: WorkflowApproveRequest,
    runs: Annotated[dict[str, WorkflowRunner], Depends(get_workflow_runs)],
) -> WorkflowSnapshot:
    runner = runs.get(run_id)
    if runner is None:
        raise UnknownWorkflowRunError(run_id)
    runner.approve(body.agent_slot_key, body.work_product_key, granted=body.granted)
    return runner.snapshot()
