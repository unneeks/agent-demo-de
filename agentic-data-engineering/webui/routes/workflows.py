"""`/workflows` -- the live multi-agent workflow dashboard.

`GET /workflows` lists in-memory runs and offers a start form -- **demo
mode only**: live mode needs a caller-named Harness/model/local-repo
config that doesn't fit a plain HTML form well, so it's reachable through
`POST /api/workflows` (see `webui/api/routes/workflows.py`), matching how
this codebase's write capabilities are already API-first everywhere else.
`GET /workflows/{run_id}` server-renders the current snapshot once, then a
small vanilla-JS poller (no framework, matching `base.html`'s existing
plain-CSS convention) re-fetches the JSON snapshot every few seconds.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from domain.metamodel.registry import MetamodelRegistry

from orchestrator.workflow import WorkflowRunner, WorkflowTemplate, start_workflow_run

from webui.api.errors import UnknownWorkflowRunError, UnknownWorkflowTemplateError
from webui.context import get_registry, get_templates, get_workflow_runs, get_workflow_templates

router = APIRouter()


@router.get("/workflows")
async def list_workflows(
    request: Request,
    templates: Annotated[dict[str, WorkflowTemplate], Depends(get_workflow_templates)],
    runs: Annotated[dict[str, WorkflowRunner], Depends(get_workflow_runs)],
    jinja: Annotated[Jinja2Templates, Depends(get_templates)],
):
    run_summaries = [runner.snapshot() for runner in runs.values()]
    return jinja.TemplateResponse(
        request,
        "workflows.html",
        {"templates": list(templates.values()), "runs": sorted(run_summaries, key=lambda s: s.started_at, reverse=True)},
    )


@router.post("/workflows/start")
async def start_workflow_from_form(
    request: Request,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    templates: Annotated[dict[str, WorkflowTemplate], Depends(get_workflow_templates)],
    runs: Annotated[dict[str, WorkflowRunner], Depends(get_workflow_runs)],
):
    form = await request.form()
    template_key = str(form.get("template_key", ""))
    template = templates.get(template_key)
    if template is None:
        raise UnknownWorkflowTemplateError(template_key)
    runner = start_workflow_run(run_id=None, template=template, registry=registry, mode="demo")
    runs[runner.snapshot().run_id] = runner
    return RedirectResponse(url=f"/workflows/{runner.snapshot().run_id}", status_code=303)


@router.get("/workflows/{run_id}")
async def workflow_dashboard(
    request: Request,
    run_id: str,
    runs: Annotated[dict[str, WorkflowRunner], Depends(get_workflow_runs)],
    jinja: Annotated[Jinja2Templates, Depends(get_templates)],
):
    runner = runs.get(run_id)
    if runner is None:
        raise UnknownWorkflowRunError(run_id)
    snapshot = runner.snapshot()
    return jinja.TemplateResponse(
        request,
        "workflow_dashboard.html",
        {
            "run_id": run_id,
            "run_id_json": _embeddable_json(run_id),
            "snapshot": snapshot,
            # Jinja2Templates has no `tojson` filter (that's Flask-specific),
            # so the initial render's JSON is serialized here, once, in
            # Python -- the same payload shape the JS poller's own `fetch`
            # calls receive from the JSON API.
            "snapshot_json": _embeddable_json(dataclasses.asdict(snapshot), default=str),
        },
    )


def _embeddable_json(value: object, **dumps_kwargs: object) -> str:
    """`json.dumps()`, safe to inline inside a `<script>` block. In demo
    mode every string here is our own registry data, but a live run's
    `current_activity`/error text can contain arbitrary LLM output -- a
    `</script>` substring in that text would otherwise close the tag early
    and let the rest execute as page HTML."""
    return json.dumps(value, **dumps_kwargs).replace("</", "<\\/")
