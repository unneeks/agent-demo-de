"""EngineeringObservation -- one concrete instance of recurring engineering
activity, read directly off a project's already-ingested graph.

Deliberately not the existing ``Observation`` (``domain/metamodel/entities/
shared/work.py``): that entity is a runtime drift/failure/correction signal
with ``UPDATES`` edges proposing a change to a twin. An ``EngineeringObservation``
proposes nothing and updates nothing -- it is raw material a pattern-discovery
pass groups, nothing more.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, ProvenancedEntity, new_ulid
from domain.metamodel.enums import EntityType, Twin


class EngineeringObservation(ProvenancedEntity):
    """One instance of recurring engineering activity, transcribed from an
    already-ingested technical or delivery entity.

    ``confidence``/``evidence_refs``/``discovered_at`` are inherited from
    ``Provenanced``, not redeclared. There is no separate ``observed_at``:
    this codebase has no telemetry that would let "when the activity
    happened" differ meaningfully from "when it was read off the graph",
    so ``Provenanced.discovered_at`` already serves that role. ``frequency``
    lives only on ``EngineeringPattern`` -- never denormalized here, where
    it could drift out of sync with the actual grouping.
    """

    entity_type: EntityType = EntityType.ENGINEERING_OBSERVATION
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    project_ref: EntityRef
    #: The technical/delivery entity this was mined from.
    source_ref: EntityRef
    source_type: str = Field(
        description="pipeline | test | delivery_task | delivery_activity"
    )
    activity: str = Field(min_length=1, description="Normalized activity label.")
    actor: str | None = None
    technology: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    sequence: int | None = Field(default=None, ge=0)
    outcome: str | None = None
