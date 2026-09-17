"""Relationships as first-class metadata objects.

An edge is not a pointer -- it is a record with its own provenance, confidence,
discoverer and validity window. "This pipeline depends on that table" is a
*claim*, and the platform must know whether it was read from a dbt manifest or
guessed from a naming convention.

That matters twice as much with two twins. "This architecture document describes
this pipeline" is almost always inferred, and an impact analysis that treats it
as certain will tell someone to update a document that was never about their
code.

The vocabulary lives in ``metamodel-registry/relationship_types.yaml``. Adding
``MONITORS`` is a data change. See ADR-0004.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from pydantic import Field, model_validator

from domain.metamodel.base import EntityRef, MetamodelModel, Provenanced, new_ulid
from domain.metamodel.enums import EntityType, ProvenanceState, Twin

if TYPE_CHECKING:
    from domain.metamodel.registry import MetamodelRegistry


class RelationshipTypeSpec(MetamodelModel):
    """The declaration of one legal relationship type, loaded from YAML."""

    key: str = Field(min_length=1)
    description: str | None = None
    source_types: list[EntityType] = Field(min_length=1)
    target_types: list[EntityType] = Field(min_length=1)
    cardinality: str = Field(default="many", description="one | many")
    #: Structural relationships (Agent HAS_SKILL Skill) are configuration and
    #: need no provenance. Discovered ones (Pipeline DEPENDS_ON DataAsset) do.
    requires_provenance: bool = True
    symmetric: bool = False
    #: Which dimension this edge lives in. ``CROSS`` edges join the two twins
    #: and are the ones that make the dual model worth having; ``SHARED`` edges
    #: belong to neither exclusively (evaluation, evidence, context).
    dimension: str = Field(
        default="TECHNICAL", description="TECHNICAL | DELIVERY | CROSS | SHARED"
    )

    @model_validator(mode="after")
    def _validate_enumerations(self) -> Self:
        if self.cardinality not in ("one", "many"):
            raise ValueError(
                f"relationship type {self.key!r}: cardinality must be 'one' or 'many', "
                f"got {self.cardinality!r}"
            )
        if self.dimension not in ("TECHNICAL", "DELIVERY", "CROSS", "SHARED"):
            raise ValueError(
                f"relationship type {self.key!r}: dimension must be TECHNICAL, DELIVERY, "
                f"CROSS or SHARED, got {self.dimension!r}"
            )
        return self

    def permits(self, source: EntityType, target: EntityType) -> bool:
        return source in self.source_types and target in self.target_types

    @property
    def is_cross_twin(self) -> bool:
        return self.dimension == "CROSS"


class Relationship(Provenanced):
    """A typed, provenanced edge between two entities.

    Registry validation is a separate step rather than something the constructor
    does, so an edge written under an older registry version can still be
    deserialized from storage and inspected instead of failing to load.
    """

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    type: str = Field(min_length=1, description="Relationship type key, e.g. 'DEPENDS_ON'.")
    source: EntityRef
    target: EntityRef
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

    def validate_against(self, registry: MetamodelRegistry) -> Self:
        """Check this edge against the relationship-type registry."""
        spec = registry.relationship_type(self.type)
        if spec is None:
            raise ValueError(
                f"unknown relationship type {self.type!r}; add it to "
                "metamodel-registry/relationship_types.yaml rather than to code"
            )

        if not spec.permits(self.source.type, self.target.type):
            raise ValueError(
                f"{self.type} does not permit {self.source.type.value} -> "
                f"{self.target.type.value}. Allowed: "
                f"{[s.value for s in spec.source_types]} -> "
                f"{[t.value for t in spec.target_types]}"
            )

        if (
            spec.requires_provenance
            and self.provenance is ProvenanceState.INFERRED
            and self.confidence is None
        ):
            raise ValueError(f"{self.type} edge is INFERRED and needs a confidence score")

        return self

    @property
    def key(self) -> tuple[str, str, str]:
        """Natural key: an edge is identified by its endpoints and its type."""
        return (str(self.source.identity), self.type, str(self.target.identity))

    def __str__(self) -> str:
        marker = "" if self.is_factual else f" (~{self.confidence})"
        return f"({self.source})-[{self.type}{marker}]->({self.target})"


def relationship(
    type_: str,
    source: EntityRef,
    target: EntityRef,
    *,
    provenance: ProvenanceState = ProvenanceState.OBSERVED,
    discovered_by: str = "platform",
    confidence: float | None = None,
    **kwargs: object,
) -> Relationship:
    """Convenience constructor for the common case.

    Defaults to ``OBSERVED`` with a named discoverer, because most edges created
    in code are structural configuration rather than inference.
    """
    return Relationship(
        type=type_,
        source=source,
        target=target,
        provenance=provenance,
        discovered_by=discovered_by,
        confidence=confidence,
        **kwargs,  # type: ignore[arg-type]
    )


#: Edge types that carry impact from a technical change into delivery
#: obligations. The impact engine walks these to answer "what does the process
#: now require of me?" See ``engines/impact/``.
DELIVERY_IMPACT_EDGES: tuple[str, ...] = (
    "GOVERNS",
    "DESCRIBES",
    "TRIGGERS_TASK",
    "VALIDATED_BY",
    "ENDS_AT_GATE",
    "REQUIRES_EVIDENCE",
)

#: The traceability chain, in order (§27). ``trace()`` follows these edge types
#: from a Requirement to a Deployment, reporting where the chain breaks.
TRACEABILITY_CHAIN: tuple[tuple[str, EntityType], ...] = (
    ("TRACED_TO", EntityType.DELIVERY_TASK),
    ("PERFORMED_BY", EntityType.AGENT),
    ("PRODUCES_ARTIFACT", EntityType.DELIVERY_ARTIFACT),
    ("VERIFIED_BY", EntityType.TEST),
    ("GENERATES", EntityType.EVIDENCE),
    ("SUPPORTS_APPROVAL", EntityType.APPROVAL),
    ("AUTHORIZES", EntityType.DEPLOYMENT),
)


def twin_of(entity_type: EntityType, registry: MetamodelRegistry | None = None) -> Twin:
    """Which twin an entity type belongs to.

    Reads the class default rather than duplicating the mapping, so it cannot
    drift from the entities themselves.
    """
    from domain.metamodel.entities import ENTITY_CLASSES

    cls = ENTITY_CLASSES.get(entity_type)
    if cls is None:
        return Twin.SHARED
    return cls.model_fields["twin"].default
