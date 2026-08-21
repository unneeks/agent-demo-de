"""Evaluation, Evidence and Finding.

Phase 1 models evaluation; it does not run it. What exists here is the
vocabulary the harness will populate, including the addendum's second scoring
dimension: an agent is measured on technical performance *and* delivery
conformance, and cannot certify on the first alone (§28).
"""

from domain.metamodel.entities.evaluation.evaluation import (
    Evaluation,
    EvaluationMetric,
    EvaluationScenario,
    EvaluationSuite,
    MetricResult,
)
from domain.metamodel.entities.evaluation.evidence import Evidence, Finding

__all__ = [
    "Evaluation",
    "EvaluationMetric",
    "EvaluationScenario",
    "EvaluationSuite",
    "Evidence",
    "Finding",
    "MetricResult",
]
