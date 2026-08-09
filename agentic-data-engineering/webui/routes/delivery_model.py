"""GET /delivery-models and /delivery-models/{model_key} -- the catalog-level
delivery model: phases, tasks, checklists and gates. All catalog data, not
project-scoped -- no writes, no project context needed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.registry import MetamodelRegistry
from engines.gates.checklists import machine_evaluable_share

from webui.context import get_registry, get_templates
from webui.errors import UnknownDeliveryModelError

router = APIRouter()


@router.get("/delivery-models")
async def delivery_model_index(
    request: Request,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
):
    models = [
        {"key": key, "name": loaded.model.name, "methodology": loaded.methodology.name if loaded.methodology else None}
        for key, loaded in sorted(registry.delivery_models.items())
    ]
    return templates.TemplateResponse(request, "delivery_model_index.html", {"models": models})


@router.get("/delivery-models/{model_key}")
async def delivery_model_detail(
    model_key: str,
    request: Request,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
):
    loaded = registry.delivery_model(model_key)
    if loaded is None:
        raise UnknownDeliveryModelError(model_key)

    phases = []
    for phase in loaded.phases_in_order():
        tasks = [t for t in loaded.tasks.values() if phase.phase_key in t.phase_keys]
        gates = [g for g in loaded.gates.values() if phase.phase_key in g.phase_keys]
        phases.append({"phase": phase, "tasks": tasks, "gates": gates})

    checklists = []
    for key, checklist in sorted(loaded.checklists.items()):
        checklist_items = loaded.items_for(key)
        checklists.append(
            {
                "checklist": checklist,
                "checklist_items": checklist_items,
                "machine_evaluable_share": machine_evaluable_share(checklist_items),
            }
        )

    return templates.TemplateResponse(
        request,
        "delivery_model_detail.html",
        {
            "model_key": model_key,
            "model": loaded.model,
            "phases": phases,
            "checklists": checklists,
            "gates": sorted(loaded.gates.values(), key=lambda g: g.gate_key),
        },
    )
