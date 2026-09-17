"""Infrastructure, CloudResource and ArchitectureElement."""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, ProvenancedEntity
from domain.metamodel.enums import EntityType, Twin


class Infrastructure(ProvenancedEntity):
    """A declared infrastructure component, usually from IaC."""

    entity_type: EntityType = EntityType.INFRASTRUCTURE
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    infrastructure_kind: str = Field(description="terraform_module | helm_chart | compose_service")
    source_path: str | None = None
    #: Capability keys this infrastructure realizes, never vendor service names.
    #: Vendors live in TechnologyBinding.
    capability_keys: list[str] = Field(default_factory=list)
    manages_refs: list[EntityRef] = Field(default_factory=list)


class CloudResource(ProvenancedEntity):
    """A concrete provisioned resource.

    ``resource_type`` is intentionally free text -- it is the vendor's word for
    the thing. The platform reasons about ``capability_keys``; only
    TechnologyBinding maps a capability to a vendor service. See ADR-0005.
    """

    entity_type: EntityType = EntityType.CLOUD_RESOURCE
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    platform_key: str | None = None
    resource_type: str = Field(min_length=1)
    resource_id: str | None = None
    region: str | None = None
    capability_keys: list[str] = Field(default_factory=list)
    managed_by_ref: EntityRef | None = Field(
        default=None, description="Infrastructure that declares this resource, if any."
    )
    cost_centre: str | None = None


class ArchitectureElement(ProvenancedEntity):
    """A component or decision in the technical architecture.

    The bridge to the Delivery Twin: a DeliveryArtifact (an architecture
    document produced by a delivery task) DESCRIBES one of these, and this in
    turn is IMPLEMENTED_BY pipelines and resources. That path is what makes
    "is the architecture document still true?" an answerable question.
    """

    entity_type: EntityType = EntityType.ARCHITECTURE_ELEMENT
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    element_kind: str = Field(description="component | layer | pattern | decision | integration")
    #: Concrete things realizing this element.
    implemented_by_refs: list[EntityRef] = Field(default_factory=list)
    #: The delivery artifact (document) that specifies it, if one was found.
    specified_by_ref: EntityRef | None = None
    capability_keys: list[str] = Field(default_factory=list)
    status: str | None = Field(default=None, description="proposed | current | deprecated")
