"""DataAsset, Pipeline and SchemaDefinition.

``DataAsset`` deliberately covers dataset, table, view, topic, file, column and
data product through ``asset_kind`` plus a self-nesting ``parent_ref``, rather
than one entity type per level. A column is not conceptually different from a
table for the purposes of provenance, lineage or impact -- it is a node with a
parent -- and separate types would multiply the relationship vocabulary without
adding meaning. See ADR-0010.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel, ProvenancedEntity
from domain.metamodel.enums import EntityType, Twin


class SchemaField(MetamodelModel):
    """One field in a schema definition."""

    name: str = Field(min_length=1)
    data_type: str
    nullable: bool = True
    description: str | None = None
    classification: str | None = Field(
        default=None, description="Sensitivity classification, e.g. 'PII'."
    )


class SchemaDefinition(ProvenancedEntity):
    """The shape of a data asset at a point in time.

    Held separately from the asset so schema *change* is a first-class fact:
    comparing two versions is how schema-drift detection and contract testing
    work.
    """

    entity_type: EntityType = EntityType.SCHEMA_DEFINITION
    twin: Twin = Twin.TECHNICAL

    asset_ref: EntityRef
    fields: list[SchemaField] = Field(default_factory=list)
    fingerprint: str | None = Field(
        default=None, description="Stable hash of the field list, for cheap drift detection."
    )

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


class DataAsset(ProvenancedEntity):
    """A dataset, table, view, topic, file, column or data product."""

    entity_type: EntityType = EntityType.DATA_ASSET
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    asset_kind: str = Field(
        description="dataset | table | view | topic | file | column | data_product",
    )
    qualified_name: str | None = Field(
        default=None, description="Fully qualified name in its native system."
    )
    #: Containing asset -- a column's table, a table's dataset. Self-nesting.
    parent_ref: EntityRef | None = None
    schema_ref: EntityRef | None = None
    is_data_product: bool = False
    classification: str | None = None
    location: str | None = None
    owners: list[str] = Field(default_factory=list)
    consumers: list[EntityRef] = Field(default_factory=list)


class Pipeline(ProvenancedEntity):
    """A unit of orchestrated data movement or transformation."""

    entity_type: EntityType = EntityType.PIPELINE
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    pipeline_kind: str = Field(
        description="dbt_model | airflow_dag | dataflow_job | script | notebook | unknown",
    )
    source_path: str | None = None
    code_ref: EntityRef | None = None
    schedule: str | None = None
    #: Read straight from a manifest where available. The graph projection turns
    #: these into first-class DEPENDS_ON relationships with provenance attached.
    input_refs: list[EntityRef] = Field(default_factory=list)
    output_refs: list[EntityRef] = Field(default_factory=list)
    orchestrator: str | None = None
    owners: list[str] = Field(default_factory=list)
    criticality: str | None = None
