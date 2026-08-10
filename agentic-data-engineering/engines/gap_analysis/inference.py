"""Coarse maturity inference for technical and delivery capabilities.

Both functions are evidence-counting proxies, not certified assessments --
neither ever returns 5 ("optimizing"), which requires human judgment/trend
data this platform doesn't have. See docs/gap-analysis.md.

Deliberately does not reuse `ProjectGraphService.assess_readiness()`/
`GateReadiness.status` as the delivery-capability signal: four of
`GateState`'s six dimensions have no real assembler anywhere in this
codebase (`docs/orchestrator.md`'s "what this is not"), so using full gate
readiness here would silently launder that gap into a new engine.
`infer_delivery_maturity` instead uses only the one honestly-computable
signal that ties to a specific capability: real, persisted `Evaluation`s
against the capability's governing `DeliveryContract`s.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.entities.technical import Pipeline, Test
from domain.metamodel.enums import EntityType
from engines.evaluation import passed_evaluation_keys


def _matches_any_hint(pipeline: Pipeline, hints: Iterable[str]) -> bool:
    haystack = " ".join(
        filter(None, [pipeline.pipeline_kind, pipeline.orchestrator, pipeline.source_path])
    ).lower()
    return any(hint.lower() in haystack for hint in hints)


def _is_covered(pipeline: Pipeline, tests: Iterable[Test]) -> bool:
    pipeline_ref = EntityRef(type=EntityType.PIPELINE, id=pipeline.id)
    return any(pipeline_ref in test.covers_refs for test in tests)


def infer_technical_maturity(
    detection_hints: tuple[str, ...],
    pipelines: list[Pipeline],
    tests: list[Test],
) -> int:
    """0 if nothing in `pipelines` matches a hint; else 1-4, scaling with the
    fraction of matching pipelines a `Test.covers_refs` actually covers.

    Never returns 5 -- matching hints and test coverage are presence
    signals, not a certification of process maturity.
    """
    if not detection_hints:
        return 0
    matching = [p for p in pipelines if _matches_any_hint(p, detection_hints)]
    if not matching:
        return 0
    fraction = sum(1 for p in matching if _is_covered(p, tests)) / len(matching)
    return min(4, 1 + round(fraction * 3))


def infer_delivery_maturity(
    governing_contract_keys: list[str],
    evaluations: list[Evaluation],
) -> int:
    """0 if the capability governs no task with a real `DeliveryContract`, or
    none of those contracts has ever been evaluated; else 1-4, scaling with
    the fraction of governing contracts whose latest evaluation passed.

    Reuses `passed_evaluation_keys()` (Phase 5) per contract subject rather
    than reimplementing "latest evaluation per subject wins" here.
    """
    if not governing_contract_keys:
        return 0
    passing = sum(
        1
        for key in governing_contract_keys
        if passed_evaluation_keys(
            evaluations, subject_ref=EntityRef(type=EntityType.DELIVERY_CONTRACT, id=key)
        )
    )
    if passing == 0:
        return 0
    fraction = passing / len(governing_contract_keys)
    return min(4, 1 + round(fraction * 3))


__all__ = ["infer_delivery_maturity", "infer_technical_maturity"]
