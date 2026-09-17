"""EVALUATE: running a suite and persisting the result -- the write path
`engines/evaluation`'s own docs deferred to "future orchestrator work."

`observed_values` is never touched or synthesized here -- plain caller input
straight through to `run_suite()`, exactly as that function itself already
requires. This module only adds what `engines/evaluation` deliberately left
out: persisting the resulting `Evaluation`, the `EVALUATES` edge to its
subject, and (if requested) the advanced `Agent`'s new status.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.organization import Agent
from domain.metamodel.enums import AgentLifecycle
from domain.metamodel.registry import MetamodelRegistry
from domain.metamodel.relationships import relationship
from engines.evaluation import advance_agent, run_suite
from project_graph.service import ProjectGraphService

from orchestrator.result import EvaluationOutcome

_DISCOVERED_BY = "orchestrator@0.1.0"


@dataclass(frozen=True)
class EvaluationRequest:
    suite_key: str
    subject_ref: EntityRef
    observed_values: dict[str, float]
    evidence_refs: list[EntityRef] | None = None
    component_versions: dict[str, str] | None = None
    evaluated_at: datetime | None = None
    #: When set, must be the real `registry.agents[...]` object --
    #: `advance_agent()` mutates it in place, and nothing else in this
    #: codebase holds a second copy to keep in sync.
    advance_agent: Agent | None = None
    advance_to: AgentLifecycle | None = None


def run_evaluations(
    service: ProjectGraphService,
    registry: MetamodelRegistry,
    requests: Iterable[EvaluationRequest],
) -> list[EvaluationOutcome]:
    """Run each request's suite, persist the Evaluation + EVALUATES edge, and
    (if requested) advance the Agent's lifecycle and persist its new status.
    """
    outcomes: list[EvaluationOutcome] = []

    for request in requests:
        suite = registry.evaluation_suites[request.suite_key]
        evaluation = run_suite(
            suite,
            registry.evaluation_metrics,
            request.subject_ref,
            request.observed_values,
            evidence_refs=request.evidence_refs,
            component_versions=request.component_versions,
            evaluated_at=request.evaluated_at,
        )
        service.ingest_entity(evaluation)
        service.ingest_relationship(
            relationship(
                "EVALUATES",
                evaluation.ref(),
                request.subject_ref,
                discovered_by=_DISCOVERED_BY,
            ),
            registry,
        )

        advancement = None
        if request.advance_agent is not None and request.advance_to is not None:
            advancement = advance_agent(request.advance_agent, request.advance_to, evaluation=evaluation)
            service.ingest_entity(request.advance_agent)

        outcomes.append(
            EvaluationOutcome(
                suite_key=request.suite_key,
                subject_ref=request.subject_ref,
                evaluation=evaluation,
                advancement=advancement,
            )
        )

    return outcomes
