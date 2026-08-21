"""GET /projects/{project_id}/gates/{gate_key} -- live gate readiness.

Calls `orchestrator.gate.assess_gate_readiness()` directly, unmodified,
with a `GateRequest` whose four caller-supplied-only fields
(`present_artifact_kinds`, `checklist_outcomes`, `satisfied_evidence`,
`approvals`) are left at their empty defaults -- never invented.

Honesty finding, verified directly against `engines/gates/readiness.py`'s
`_score()` and `ApprovalGate._gate_must_require_something`: because a real
gate is only guaranteed to require *something* in at least one of six
fields (not all six), and this route always supplies empty state for four
of `GateState`'s dimensions, a resulting 100% for ARTIFACTS/CHECKLISTS/
EVIDENCE/APPROVALS means "this gate happens to require nothing here"
(trivially satisfied, per `_score()`'s own docstring), and any other score
for those four means "this dashboard has no way to detect what was
produced" -- never a verified finding either way. The template carries an
unconditional banner saying so, not a per-score caveat.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import MetamodelRegistry
from persistence.ports import MetadataRepository
from project_graph.errors import UnknownProjectError
from project_graph.service import ProjectGraphService

from orchestrator.gate import GateRequest, assess_gate_readiness

from webui.constants import UNASSESSABLE_DIMENSIONS
from webui.context import get_metadata, get_registry, get_service, get_templates
from webui.errors import UnknownDeliveryModelError

router = APIRouter()


@router.get("/projects/{project_id}/gates/{gate_key}")
async def gate_readiness_view(
    project_id: str,
    gate_key: str,
    request: Request,
    service: Annotated[ProjectGraphService, Depends(get_service)],
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    model: str | None = None,
    evaluation_subject: str | None = None,
):
    if metadata.get(EntityType.PROJECT, project_id) is None:
        raise UnknownProjectError(EntityRef(type=EntityType.PROJECT, id=project_id))

    model_key = model
    if model_key is None:
        if len(registry.delivery_models) == 1:
            model_key = next(iter(registry.delivery_models))
        else:
            raise UnknownDeliveryModelError(
                "(none specified -- pass ?model=<key>; more than one delivery model is loaded)"
            )
    delivery_model = registry.delivery_model(model_key)
    if delivery_model is None:
        raise UnknownDeliveryModelError(model_key)

    evaluation_subject_ref = EntityRef.parse(evaluation_subject) if evaluation_subject else None
    gate_request = GateRequest(gate_key=gate_key, evaluation_subject_ref=evaluation_subject_ref)

    project_ref = EntityRef(type=EntityType.PROJECT, id=project_id)
    readiness = assess_gate_readiness(service, metadata, delivery_model, project_ref, gate_request)

    return templates.TemplateResponse(
        request,
        "gate_readiness.html",
        {
            "project_id": project_id,
            "model_key": model_key,
            "readiness": readiness,
            "unassessable_dimensions": UNASSESSABLE_DIMENSIONS,
        },
    )
