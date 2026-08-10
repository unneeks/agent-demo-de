"""Evaluation suites, scenarios, metrics and results.

Evaluation is core, not an afterthought: no agent is deployable without a
passing evaluation, and ``Deployment`` enforces that structurally.

The addendum adds a second dimension. An agent that produces technically correct
output while ignoring mandatory delivery controls must not earn a high trust
score, so metrics carry a ``dimension`` and the overall score is gated on both
(§28).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import (
    EntityRef,
    MetamodelEntity,
    MetamodelModel,
    new_ulid,
    utc_now,
)
from domain.metamodel.enums import EntityType, Twin


class EvaluationMetric(MetamodelEntity):
    """One measurable dimension with the threshold that counts as passing."""

    entity_type: EntityType = EntityType.EVALUATION_METRIC
    twin: Twin = Twin.SHARED

    metric_key: str = Field(min_length=1)
    #: "technical" or "delivery". Both are scored; neither may be traded off
    #: against the other.
    dimension: str = Field(default="technical", description="technical | delivery")
    threshold: float
    #: Most metrics improve upward; error rates and cost improve downward.
    higher_is_better: bool = True
    weight: float = Field(default=1.0, ge=0.0)
    unit: str | None = None
    blocking: bool = True

    def passes(self, value: float) -> bool:
        return value >= self.threshold if self.higher_is_better else value <= self.threshold

    @model_validator(mode="after")
    def _dimension_must_be_known(self) -> EvaluationMetric:
        if self.dimension not in ("technical", "delivery"):
            raise ValueError(
                f"metric {self.metric_key!r}: dimension must be 'technical' or 'delivery', "
                f"got {self.dimension!r}"
            )
        return self


class EvaluationScenario(MetamodelEntity):
    """A single test case: given this input, expect this behaviour."""

    entity_type: EntityType = EntityType.EVALUATION_SCENARIO
    twin: Twin = Twin.SHARED

    scenario_key: str = Field(min_length=1)
    inputs: dict[str, object] = Field(default_factory=dict)
    expected_behavior: str | None = None
    expected_output: dict[str, object] | None = None
    #: Scenarios that must fail safely matter as much as happy paths.
    expects_refusal: bool = False
    #: A scenario can require that the agent honoured a delivery control --
    #: e.g. refused to proceed past a blocking gate.
    expects_gate_respected: str | None = None
    metric_keys: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvaluationSuite(MetamodelEntity):
    """A named, versioned collection of scenarios and metrics."""

    entity_type: EntityType = EntityType.EVALUATION_SUITE
    twin: Twin = Twin.SHARED

    suite_key: str = Field(min_length=1)
    level: str = Field(description="skill | tool | agent | workflow | ecosystem")
    scenario_refs: list[EntityRef] = Field(default_factory=list)
    metric_refs: list[EntityRef] = Field(default_factory=list)
    passing_score: float = Field(default=0.8, ge=0.0, le=1.0)
    #: Separate bar for the delivery dimension, so a strong technical score
    #: cannot carry a weak conformance score.
    passing_delivery_score: float = Field(default=0.9, ge=0.0, le=1.0)
    applies_to: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _level_must_be_known(self) -> EvaluationSuite:
        allowed = {"skill", "tool", "agent", "workflow", "ecosystem"}
        if self.level not in allowed:
            raise ValueError(f"level must be one of {sorted(allowed)}, got {self.level!r}")
        return self


class MetricResult(MetamodelModel):
    """The measured value of one metric in one evaluation run."""

    metric_key: str = Field(min_length=1)
    dimension: str = "technical"
    value: float
    threshold: float
    passed: bool
    weight: float = Field(default=1.0, ge=0.0)
    blocking: bool = True
    detail: str | None = None


class Evaluation(MetamodelEntity):
    """The result of running a suite against a subject."""

    entity_type: EntityType = EntityType.EVALUATION
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    suite_ref: EntityRef
    subject_ref: EntityRef
    evaluated_at: datetime = Field(default_factory=utc_now)
    metric_results: list[MetricResult] = Field(default_factory=list)

    score: float = Field(ge=0.0, le=1.0, description="Technical dimension score.")
    delivery_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Delivery conformance score."
    )
    passed: bool
    evidence_refs: list[EntityRef] = Field(default_factory=list)
    component_versions: dict[str, str] = Field(default_factory=dict)

    @property
    def trust_score(self) -> float:
        """Overall trust, limited by the weaker dimension.

        Deliberately the minimum rather than a weighted average: averaging would
        let a 98% technical score paper over a 40% conformance score, which is
        precisely the outcome §28 forbids.
        """
        return min(self.score, self.delivery_score)

    @model_validator(mode="after")
    def _blocking_failure_fails_the_run(self) -> Evaluation:
        blocking_failed = [r.metric_key for r in self.metric_results if r.blocking and not r.passed]
        if blocking_failed and self.passed:
            raise ValueError(
                "evaluation cannot be marked passed while blocking metrics failed: "
                f"{sorted(blocking_failed)}"
            )
        return self

    @staticmethod
    def weighted_score(results: list[MetricResult], dimension: str | None = None) -> float:
        """Weighted pass rate, optionally for one dimension. Deterministic."""
        selected = [r for r in results if dimension is None or r.dimension == dimension]
        total = sum(r.weight for r in selected)
        if total <= 0:
            return 0.0
        return sum(r.weight for r in selected if r.passed) / total
