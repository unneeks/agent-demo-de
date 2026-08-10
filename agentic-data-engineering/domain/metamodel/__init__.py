"""The metamodel: the durable core of the platform.

Two twins, one graph. Agents, LLMs, clouds and tools are replaceable; the
metamodel, the dual digital twin, the capability graph, the delivery model and
the evidence model are not.
"""

from domain.metamodel.base import (
    Blockable,
    EntityRef,
    Identified,
    MetamodelEntity,
    MetamodelModel,
    Provenanced,
    ProvenancedEntity,
    SemVer,
    Versioned,
    new_ulid,
    utc_now,
)
from domain.metamodel.enums import EntityType, ProvenanceState, Twin
from domain.metamodel.version import METAMODEL_VERSION, is_compatible, require_compatible

__all__ = [
    "METAMODEL_VERSION",
    "Blockable",
    "EntityRef",
    "EntityType",
    "Identified",
    "MetamodelEntity",
    "MetamodelModel",
    "Provenanced",
    "ProvenanceState",
    "ProvenancedEntity",
    "SemVer",
    "Twin",
    "Versioned",
    "is_compatible",
    "new_ulid",
    "require_compatible",
    "utc_now",
]
