"""POST /api/projects/{project_id}/gates/{gate_key}/assess -- the one
endpoint that finally makes `GateState`'s four caller-supplied-only
dimensions (`present_artifact_kinds`, `checklist_outcomes`,
`satisfied_evidence`, `approvals`) real. `GET .../gates/{gate_key}`
(webui/api/routes/reads.py) always supplies empty state, exactly like its
HTML counterpart -- this POST is the only place a caller's real state is
ever honored.

`ChecklistOutcome` is accepted uncritically here, matching `GateRequest`'s
own existing shape exactly -- not recomputed or verified against
`evaluate_checklist()`. A caller can submit an internally-inconsistent or
fabricated `ChecklistOutcome`; this endpoint does not check it. See
docs/api-gateway.md's "what this is not."
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import MetamodelRegistry
from engines.gates import GateReadiness
from persistence.ports import MetadataRepository
from project_graph.errors import UnknownProjectError
from project_graph.service import ProjectGraphService

from orchestrator.gate import assess_gate_readiness

from webui.api.schemas import GateAssessRequest
from webui.api.translate import build_gate_request
from webui.context import get_metadata, get_registry, get_service
from webui.errors import UnknownDeliveryModelError

router = APIRouter(prefix="/api")


@router.post("/projects/{project_id}/gates/{gate_key}/assess")
async def assess_gate(
    project_id: str,
    gate_key: str,
    body: GateAssessRequest,
    service: Annotated[ProjectGraphService, Depends(get_service)],
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    model: str | None = None,
) -> GateReadiness:
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

    gate_request = build_gate_request(gate_key, body)
    project_ref = EntityRef(type=EntityType.PROJECT, id=project_id)
    return assess_gate_readiness(service, metadata, delivery_model, project_ref, gate_request)
