"""DataProfile -- the statistical shape of a data asset at a point in time.

Held separately from ``DataAsset`` for the same reason ``SchemaDefinition`` is:
comparing two profiles is how *quality drift* becomes a first-class fact rather
than an opaque sentence in an ``Evidence.excerpt``. "Null rate on this column
jumped from 0.2% to 8% between last week's profile and this one" is a claim that
needs two structured records to compare, not a paragraph.

``metrics`` is deliberately free-form rather than a fixed schema of named fields:
profiling metrics vary by column type (a numeric column has min/max/mean, a
string column has length distributions, a categorical column has cardinality),
and forcing them into a rigid shape would mean either a wide sparse record or a
metric type per column kind. A `dict[str, float]` keyed by metric name mirrors
``Observation.metrics`` exactly, for the same reason.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from domain.metamodel.base import EntityRef, ProvenancedEntity, utc_now
from domain.metamodel.enums import EntityType, Twin


class DataProfile(ProvenancedEntity):
    """A structured profiling result for one data asset."""

    entity_type: EntityType = EntityType.DATA_PROFILE
    twin: Twin = Twin.TECHNICAL

    asset_ref: EntityRef
    #: Free-form metric name -> value, e.g. {"row_count": 48213, "null_rate": 0.002,
    #: "distinct_count": 512, "min": 0.0, "max": 999.5}. Column-level profiles use
    #: qualified keys like "customer_id.null_rate" when the asset_ref is a table.
    metrics: dict[str, float] = Field(default_factory=dict)
    profiled_at: datetime = Field(default_factory=utc_now)
    sample_size: int | None = Field(
        default=None, ge=0, description="Rows actually sampled, if less than the full asset."
    )
    profiling_tool: str | None = None
