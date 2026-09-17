"""Running an `EvaluationSuite` against a subject, and reducing evaluation
history into the passed-suite-key set `GateState` needs.

Pure: no I/O, no `ProjectGraphService`. `observed_values` is always caller-
supplied -- this module never scores anything itself, matching how
`engines/composition/resolution.py` reuses `EngineeringRole.is_satisfied_by()`
rather than reimplementing role satisfaction. Here the pre-existing pure
primitives are `EvaluationMetric.passes()` and `Evaluation.weighted_score()`
(`domain/metamodel/entities/evaluation/evaluation.py`) -- this module is a
thin orchestration layer over both, not a third scoring implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from domain.metamodel.base import EntityRef, new_ulid, utc_now
from domain.metamodel.entities.evaluation import Evaluation, EvaluationMetric, EvaluationSuite, MetricResult
from domain.metamodel.enums import EntityType


def run_suite(
    suite: EvaluationSuite,
    metrics: dict[str, EvaluationMetric],
    subject_ref: EntityRef,
    observed_values: dict[str, float],
    *,
    evidence_refs: list[EntityRef] | None = None,
    component_versions: dict[str, str] | None = None,
    evaluated_at: datetime | None = None,
) -> Evaluation:
    """Score one run of `suite` against `subject_ref`.

    `observed_values` maps metric_key -> observed value; this function does
    no measurement of its own. Raises `ValueError` if the suite references a
    metric not present in `metrics`, or a metric it requires has no entry in
    `observed_values` -- a suite that cannot be scored must fail loudly, not
    silently under-score.
    """
    results: list[MetricResult] = []
    for metric_ref in suite.metric_refs:
        key = metric_ref.id
        metric = metrics.get(key)
        if metric is None:
            raise ValueError(f"suite {suite.suite_key!r} references unknown metric {key!r}")
        if key not in observed_values:
            raise ValueError(
                f"no observed value supplied for metric {key!r} required by suite "
                f"{suite.suite_key!r}"
            )
        value = observed_values[key]
        results.append(
            MetricResult(
                metric_key=key,
                dimension=metric.dimension,
                value=value,
                threshold=metric.threshold,
                passed=metric.passes(value),
                weight=metric.weight,
                blocking=metric.blocking,
                detail=f"observed {value} against threshold {metric.threshold}",
            )
        )

    score = Evaluation.weighted_score(results, "technical")
    delivery_results = [r for r in results if r.dimension == "delivery"]
    # A suite with no delivery-dimension metric has nothing to score in that
    # dimension -- "requires nothing" is trivially satisfied, the same idiom
    # engines/gates/readiness.py's _score() and engines/composition/
    # resolution.py's _coverage() both use. Falling through to
    # Evaluation.weighted_score()'s literal 0.0-when-empty here would make
    # trust_score = min(score, delivery_score) collapse to 0 for every
    # purely-technical suite, which is not what an empty dimension means.
    delivery_score = Evaluation.weighted_score(results, "delivery") if delivery_results else 1.0

    blocking_failed = any(r.blocking and not r.passed for r in results)
    meets_score = score >= suite.passing_score
    meets_delivery = (not delivery_results) or (delivery_score >= suite.passing_delivery_score)
    # Computed this way specifically so the constructed Evaluation never trips
    # its own _blocking_failure_fails_the_run validator: passed is never True
    # alongside an unpassed blocking result.
    passed = meets_score and meets_delivery and not blocking_failed

    return Evaluation(
        id=new_ulid(),
        name=f"{suite.suite_key} :: {subject_ref.id}",
        entity_type=EntityType.EVALUATION,
        suite_ref=suite.ref(),
        subject_ref=subject_ref,
        evaluated_at=evaluated_at or utc_now(),
        metric_results=results,
        score=score,
        delivery_score=delivery_score,
        passed=passed,
        evidence_refs=evidence_refs or [],
        component_versions=component_versions or {},
    )


def passed_evaluation_keys(
    evaluations: Iterable[Evaluation], *, subject_ref: EntityRef | None = None
) -> set[str]:
    """Reduce evaluation history to the suite keys currently passing.

    The assembler `engines/gates/readiness.py`'s `GateState` docstring
    expects a caller to provide ("Assembled by the caller from the graph").

    Latest evaluation per suite key wins: a suite key counts as passed only
    if its most recent run (by `evaluated_at`) passed. A single lucky pass
    long ago must not paper over every run since, and a stale failure must
    not keep blocking a gate after a later run passed -- "any passing ever"
    was rejected for exactly the first reason.
    """
    filtered = [
        e for e in evaluations if subject_ref is None or e.subject_ref.id == subject_ref.id
    ]
    latest: dict[str, Evaluation] = {}
    for evaluation in filtered:
        key = evaluation.suite_ref.id
        if key not in latest or evaluation.evaluated_at > latest[key].evaluated_at:
            latest[key] = evaluation
    return {key for key, evaluation in latest.items() if evaluation.passed}
