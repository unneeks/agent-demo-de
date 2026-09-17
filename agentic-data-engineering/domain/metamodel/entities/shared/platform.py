"""Platform and TechnologyBinding -- the vendor firewall.

::

    Capability: streaming
        -> TechnologyBinding (gcp)  -> Pub/Sub + Dataflow
        -> TechnologyBinding (aws)  -> Kinesis

Agents resolve capabilities; only adapters resolve bindings. No vendor name
belongs in agent or skill logic. See ADR-0005.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import MetamodelEntity
from domain.metamodel.enums import EntityType, Twin


class Platform(MetamodelEntity):
    """An execution environment a project can be deployed onto."""

    entity_type: EntityType = EntityType.PLATFORM
    twin: Twin = Twin.SHARED

    platform_key: str = Field(min_length=1)
    vendor: str | None = None
    regions: list[str] = Field(default_factory=list)


class TechnologyBinding(MetamodelEntity):
    """Realizes one capability on one platform using specific technologies."""

    entity_type: EntityType = EntityType.TECHNOLOGY_BINDING
    twin: Twin = Twin.SHARED

    capability_key: str = Field(min_length=1)
    platform_key: str = Field(min_length=1)
    technologies: list[str] = Field(min_length=1)
    #: Hints discovery matches against repository content. Heuristics, which is
    #: why anything derived from them is INFERRED with a confidence.
    detection_hints: list[str] = Field(default_factory=list)
    notes: str | None = None
    maturity: str | None = Field(default=None, description="ga | preview | deprecated")

    @property
    def binding_key(self) -> str:
        return f"{self.capability_key}@{self.platform_key}"
