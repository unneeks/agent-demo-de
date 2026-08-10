"""``fetch_project_facts()`` -- the narrow project-graph read Foundry's
mining step needs.

Deliberately does **not** import ``webui/graph_discovery.py``, even though
that module's ``discover_project_graph()`` does almost exactly this same
traverse-then-fetch idiom: a backend orchestration package depending on
the UI layer inverts ``docs/architecture.md``'s layered diagram. This is a
small, named duplication (~15 lines) of that idiom, scoped to exactly the
four entity types mining needs, in exchange for correct dependency
direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.delivery import DeliveryActivity, DeliveryTask
from domain.metamodel.entities.technical import Pipeline, Test
from domain.metamodel.enums import EntityType
from persistence.ports import GraphRepository, MetadataRepository

#: The only entity types Foundry mining reads. Anything else reachable
#: from the project's graph node (Requirements, Evidence, catalog
#: references, ...) is out of scope for this phase.
_MINED_ENTITY_TYPES = (
    EntityType.PIPELINE,
    EntityType.TEST,
    EntityType.DELIVERY_TASK,
    EntityType.DELIVERY_ACTIVITY,
)


@dataclass(frozen=True)
class ProjectFacts:
    pipelines: list[Pipeline] = field(default_factory=list)
    tests: list[Test] = field(default_factory=list)
    delivery_tasks: list[DeliveryTask] = field(default_factory=list)
    delivery_activities: list[DeliveryActivity] = field(default_factory=list)


def fetch_project_facts(
    project_ref: EntityRef, metadata: MetadataRepository, graph: GraphRepository
) -> ProjectFacts:
    identity = project_ref.identity
    discovered: dict[str, EntityRef] = {}
    for result in graph.traverse(identity, max_depth=25, direction="both"):
        if result.ref.type in _MINED_ENTITY_TYPES:
            discovered.setdefault(str(result.ref), result.ref)

    pipelines: list[Pipeline] = []
    tests: list[Test] = []
    delivery_tasks: list[DeliveryTask] = []
    delivery_activities: list[DeliveryActivity] = []
    for ref in discovered.values():
        found = metadata.get(ref.type, ref.id)
        if found is None:
            continue
        if ref.type is EntityType.PIPELINE:
            pipelines.append(Pipeline.model_validate(found.payload))
        elif ref.type is EntityType.TEST:
            tests.append(Test.model_validate(found.payload))
        elif ref.type is EntityType.DELIVERY_TASK:
            delivery_tasks.append(DeliveryTask.model_validate(found.payload))
        elif ref.type is EntityType.DELIVERY_ACTIVITY:
            delivery_activities.append(DeliveryActivity.model_validate(found.payload))

    return ProjectFacts(
        pipelines=sorted(pipelines, key=lambda entity: entity.id),
        tests=sorted(tests, key=lambda entity: entity.id),
        delivery_tasks=sorted(delivery_tasks, key=lambda entity: entity.id),
        delivery_activities=sorted(delivery_activities, key=lambda entity: entity.id),
    )
