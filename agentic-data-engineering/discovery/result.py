"""The shapes discovery adapters and the orchestrator communicate through.

``DiscoveryResult`` is what one extraction pass produces (pure data, no I/O).
``DiscoveryReport`` is what a full ``discover_project`` run produces, after
ingestion through ``ProjectGraphService``. Between the two, ``DiscoverySkip``
and ``DiscoveryFailure`` are the two kinds of "this did not become a fact":
a skip is a soft, expected gap (an unresolved reference, a file the walk
classifier ignored); a failure is a rejected write (malformed extraction
output, a registry validation error) that could not be trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef, MetamodelEntity
from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import Relationship


@dataclass(frozen=True)
class DiscoverySkip:
    """A soft, expected gap -- not an error, just a fact nothing was found for."""

    kind: str
    detail: str
    source: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    """What one extraction pass produced: entities, relationships, and skips.

    Entities and relationships are ordered as produced -- the orchestrator is
    responsible for the entities-before-relationships ingestion discipline,
    not this container.
    """

    entities: list[MetamodelEntity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    skipped: list[DiscoverySkip] = field(default_factory=list)


@dataclass(frozen=True)
class DiscoveryFailure:
    """A write that was attempted and rejected -- never partially applied."""

    kind: str
    detail: str
    source: str


@dataclass(frozen=True)
class DiscoveryReport:
    """The outcome of one full ``discover_project`` run."""

    project_ref: EntityRef
    entities_ingested: int
    relationships_ingested: int
    entities_by_type: dict[EntityType, int]
    skipped: list[DiscoverySkip] = field(default_factory=list)
    failed: list[DiscoveryFailure] = field(default_factory=list)
