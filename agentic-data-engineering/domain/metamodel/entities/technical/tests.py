"""Test -- a test that already exists in the project.

Discovering these is what lets the platform reason about regression coverage
instead of assuming there is none. ``satisfies_requirement_refs`` is the join
into the Delivery Twin: a technical test can discharge a process control, which
is how a gate's evidence requirement gets met by something real.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, ProvenancedEntity
from domain.metamodel.enums import EntityType, TestType, Twin


class Test(ProvenancedEntity):
    entity_type: EntityType = EntityType.TEST
    twin: Twin = Twin.TECHNICAL

    project_ref: EntityRef
    test_type: TestType
    framework: str | None = Field(default=None, description="pytest | dbt | great_expectations")
    source_path: str | None = None
    #: What this test protects. Impact analysis selects tests by intersecting a
    #: change's blast radius with these refs.
    covers_refs: list[EntityRef] = Field(default_factory=list)
    #: EvidenceRequirements in the delivery model this test discharges.
    satisfies_requirement_refs: list[EntityRef] = Field(default_factory=list)
    selector: str | None = Field(
        default=None, description="How to run just this test, e.g. a pytest node id."
    )
    last_result: str | None = None
    average_runtime_seconds: float | None = Field(default=None, ge=0.0)
