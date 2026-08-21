"""The one project-graph-discovery loop, shared between the HTML route
(`webui/routes/project_graph.py`) and the JSON route
(`webui/api/routes/reads.py`) so the two surfaces can never compute this
differently. Reuses `ProjectGraphService.snapshot()`'s exact traversal and
relationship-filter shape, read-only: no `ProjectSnapshot` is built or
ingested, nothing is written. See project_graph/service.py:snapshot().
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef
from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import Relationship
from persistence.ports import GraphRepository, MetadataRepository


@dataclass(frozen=True)
class ProjectGraphDiscovery:
    entities_by_type: dict[EntityType, list[object]] = field(default_factory=dict)
    relationships_by_type: dict[str, list[Relationship]] = field(default_factory=dict)
    catalog_reference_count: int = 0


def discover_project_graph(
    project_id: str, metadata: MetadataRepository, graph: GraphRepository
) -> ProjectGraphDiscovery:
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
    relationships_by_type: dict[str, list[Relationship]] = defaultdict(list)
    for rel in project_relationships:
        relationships_by_type[rel.type].append(rel)

    return ProjectGraphDiscovery(
        entities_by_type=dict(sorted(entities_by_type.items(), key=lambda kv: kv[0].value)),
        relationships_by_type=dict(sorted(relationships_by_type.items())),
        catalog_reference_count=catalog_reference_count,
    )


__all__ = ["ProjectGraphDiscovery", "discover_project_graph"]
