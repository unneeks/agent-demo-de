"""GET /projects/{project_id} -- one project's dual-twin graph state.

Reuses `ProjectGraphService.snapshot()`'s exact traversal and relationship-
filter shape, read-only: no `ProjectSnapshot` is built or ingested, nothing
is written. See project_graph/service.py:snapshot() for the pattern this
mirrors.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from domain.metamodel.base import EntityRef
from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.enums import EntityType
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.errors import UnknownProjectError

from webui.context import get_graph, get_metadata, get_templates

router = APIRouter()


@router.get("/projects/{project_id}")
async def project_graph_view(
    project_id: str,
    request: Request,
    metadata: Annotated[MetadataRepository, Depends(get_metadata)],
    graph: Annotated[GraphRepository, Depends(get_graph)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
):
    stored_project = metadata.get(EntityType.PROJECT, project_id)
    if stored_project is None:
        raise UnknownProjectError(EntityRef(type=EntityType.PROJECT, id=project_id))

    project_ref = EntityRef(type=EntityType.PROJECT, id=project_id).identity
    discovered: dict[str, EntityRef] = {str(project_ref): project_ref}
    for result in graph.traverse(project_ref, max_depth=25, direction="both"):
        discovered.setdefault(str(result.ref), result.ref)

    entities_by_type: dict[EntityType, list[object]] = defaultdict(list)
    catalog_reference_count = 0
    for ref in discovered.values():
        found = metadata.get(ref.type, ref.id)
        if found is None:
            catalog_reference_count += 1
            continue
        entity_cls = ENTITY_CLASSES[ref.type]
        entities_by_type[ref.type].append(entity_cls.model_validate(found.payload))

    all_relationships = graph.relationships()
    project_relationships = [
        rel
        for rel in all_relationships
        if str(rel.source.identity) in discovered and str(rel.target.identity) in discovered
    ]
    relationships_by_type: dict[str, list[object]] = defaultdict(list)
    for rel in project_relationships:
        relationships_by_type[rel.type].append(rel)

    return templates.TemplateResponse(
        request,
        "project_graph.html",
        {
            "project_id": project_id,
            "entities_by_type": dict(sorted(entities_by_type.items(), key=lambda kv: kv[0].value)),
            "relationships_by_type": dict(sorted(relationships_by_type.items())),
            "catalog_reference_count": catalog_reference_count,
        },
    )
