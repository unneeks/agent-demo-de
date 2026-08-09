"""JSON mirrors of `webui/routes/*.py`'s six read-only views -- same
computation, same functions, JSON instead of Jinja2. `GET .../gates/
{gate_key}` always supplies empty `GateRequest` fields, exactly like its
HTML counterpart -- the "honest zero." `POST .../gates/{gate_key}/assess`
(webui/api/routes/gates.py) is the only place a caller's real state is
ever honored.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.entities.technical import Project
from domain.metamodel.enums import EntityType
from domain.metamodel.registry import MetamodelRegistry
from engines.gates import GateReadiness
from engines.gates.checklists import machine_evaluable_share
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.errors import UnknownProjectError
from project_graph.service import ProjectGraphService

from orchestrator.gate import GateRequest, assess_gate_readiness

from webui.constants import UNASSESSABLE_DIMENSIONS
from webui.context import get_graph, get_metadata, get_registry, get_service
from webui.errors import UnknownDeliveryModelError
from webui.graph_discovery import discover_project_graph
from webui.api.schemas import DeliveryModelDetailResponse, DeliveryModelSummary, MarketplaceResponse, ProjectGraphResponse

router = APIRouter(prefix="/api")


@router.get("/projects")
async def list_projects(
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
) -> list[Project]:
    stored = metadata.list(EntityType.PROJECT)
    return sorted((Project.model_validate(row.payload) for row in stored), key=lambda p: p.id)


@router.get("/projects/{project_id}")
async def project_graph(
    project_id: str,
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    graph: Annotated[GraphRepository, Depends(get_graph)],
) -> ProjectGraphResponse:
    if metadata.get(EntityType.PROJECT, project_id) is None:
        raise UnknownProjectError(EntityRef(type=EntityType.PROJECT, id=project_id))

    discovery = discover_project_graph(project_id, metadata, graph)
    return ProjectGraphResponse(
        project_id=project_id,
        entities_by_type={
            entity_type: [entity.model_dump(mode="json") for entity in entities]
            for entity_type, entities in discovery.entities_by_type.items()
        },
        relationships_by_type=discovery.relationships_by_type,
        catalog_reference_count=discovery.catalog_reference_count,
    )


@router.get("/delivery-models")
async def delivery_model_index(
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
) -> list[DeliveryModelSummary]:
    return [
        DeliveryModelSummary(
            key=key, name=loaded.model.name, methodology=loaded.methodology.name if loaded.methodology else None
        )
        for key, loaded in sorted(registry.delivery_models.items())
    ]


@router.get("/delivery-models/{model_key}")
async def delivery_model_detail(
    model_key: str,
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
) -> DeliveryModelDetailResponse:
    loaded = registry.delivery_model(model_key)
    if loaded is None:
        raise UnknownDeliveryModelError(model_key)

    phases = []
    for phase in loaded.phases_in_order():
        tasks = [t for t in loaded.tasks.values() if phase.phase_key in t.phase_keys]
        gates = [g for g in loaded.gates.values() if phase.phase_key in g.phase_keys]
        phases.append({"phase": phase.model_dump(mode="json"), "tasks": [t.model_dump(mode="json") for t in tasks], "gates": [g.model_dump(mode="json") for g in gates]})

    checklists = []
    for key, checklist in sorted(loaded.checklists.items()):
        checklist_items = loaded.items_for(key)
        checklists.append(
            {
                "checklist": checklist.model_dump(mode="json"),
                "checklist_items": [i.model_dump(mode="json") for i in checklist_items],
                "machine_evaluable_share": machine_evaluable_share(checklist_items),
            }
        )

    return DeliveryModelDetailResponse(
        model_key=model_key,
        model=loaded.model,
        phases=phases,
        checklists=checklists,
        gates=sorted(loaded.gates.values(), key=lambda g: g.gate_key),
    )


@router.get("/marketplace")
async def marketplace(
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    graph: Annotated[GraphRepository, Depends(get_graph)],
) -> MarketplaceResponse:
    staffing = []
    for role_key, role in sorted(registry.engineering_roles.items()):
        agent_refs = graph.neighbors(
            EntityRef(type=EntityType.ENGINEERING_ROLE, id=role_key), type_="IMPLEMENTED_BY"
        )
        staffing.append({"role": role.model_dump(mode="json"), "agent_ids": [ref.id for ref in agent_refs]})

    return MarketplaceResponse(
        agents=[a.model_dump(mode="json") for a in sorted(registry.agents.values(), key=lambda a: a.agent_key)],
        skills=[s.model_dump(mode="json") for s in sorted(registry.skills.values(), key=lambda s: s.skill_key)],
        tools=[t.model_dump(mode="json") for t in sorted(registry.tools.values(), key=lambda t: t.tool_key)],
        knowledge_packs=[
            k.model_dump(mode="json") for k in sorted(registry.knowledge_packs.values(), key=lambda k: k.knowledge_key)
        ],
        staffing=staffing,
    )


@router.get("/evaluations")
async def evaluations(
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    subject: str | None = None,
) -> list[Evaluation]:
    all_evaluations = [
        Evaluation.model_validate(row.payload) for row in metadata.list(EntityType.EVALUATION)
    ]
    if subject:
        subject_ref = EntityRef.parse(subject)  # raises ValueError -> 422, on a malformed filter
        all_evaluations = [
            e
            for e in all_evaluations
            if e.subject_ref.type == subject_ref.type and e.subject_ref.id == subject_ref.id
        ]
    all_evaluations.sort(key=lambda e: e.evaluated_at, reverse=True)
    return all_evaluations


@router.get("/projects/{project_id}/gates/{gate_key}")
async def gate_readiness_view(
    project_id: str,
    gate_key: str,
    service: Annotated[ProjectGraphService, Depends(get_service)],
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    registry: Annotated[MetamodelRegistry, Depends(get_registry)],
    model: str | None = None,
    evaluation_subject: str | None = None,
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

    evaluation_subject_ref = EntityRef.parse(evaluation_subject) if evaluation_subject else None
    gate_request = GateRequest(gate_key=gate_key, evaluation_subject_ref=evaluation_subject_ref)

    project_ref = EntityRef(type=EntityType.PROJECT, id=project_id)
    return assess_gate_readiness(service, metadata, delivery_model, project_ref, gate_request)


__all__ = ["router", "UNASSESSABLE_DIMENSIONS"]
