"""``run_foundry_cycle()`` -- mine -> discover -> synthesize -> evaluate,
every write through ``ProjectGraphService``.

Deliberately **not** called from ``orchestrator/cycle.py``: this is its
own entry point, invoked independently whenever a caller wants to look for
new marketplace opportunities against a project graph that already
exists -- see ``scripts/run_foundry.py``, the concrete "invoke any time"
CLI. The same shape of independence ``discovery.orchestrate.discover_project``
already has relative to ``orchestrator/cycle.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from domain.metamodel.base import EntityRef, utc_now
from domain.metamodel.entities.foundry import (
    CandidateAgent,
    CandidateReview,
    CandidateSkill,
    CandidateTool,
    EngineeringObservation,
    EngineeringPattern,
)
from domain.metamodel.enums import CandidateStatus, EntityType, ProvenanceState
from domain.metamodel.registry import MetamodelRegistry
from domain.metamodel.relationships import relationship
from engines.evaluation.harness import run_suite
from engines.foundry.discovery import discover_patterns
from engines.foundry.evaluation import score_candidate_completeness
from engines.foundry.lifecycle import advance_candidate
from engines.foundry.mining import mine_observations
from discovery.extraction.client import ExtractionClient
from foundry.errors import FoundryError
from foundry.project_facts import fetch_project_facts
from foundry.result import FoundryCycleFailure, FoundryCycleReport
from foundry.synthesis.prompts import build_candidate_prompt
from foundry.synthesis.parse_response import parse_candidate_content
from persistence.ports import GraphRepository, MetadataRepository
from project_graph.service import ProjectGraphService

_MINING_DISCOVERED_BY = "foundry-mining@0.1.0"
_DISCOVERY_DISCOVERED_BY = "foundry-discovery@0.1.0"
_SYNTHESIS_DISCOVERED_BY = "foundry-synthesis@0.1.0"

#: (EntityType, candidate class, embedded-payload field name, suite key)
#: for each supported candidate kind. One table, not three near-identical
#: code paths.
_KIND_CONFIG: dict[str, tuple[EntityType, type, str, str]] = {
    "skill": (EntityType.SKILL, CandidateSkill, "proposed_skill", "foundry-candidate-skill-completeness"),
    "tool": (EntityType.TOOL, CandidateTool, "proposed_tool", "foundry-candidate-tool-completeness"),
    "agent": (EntityType.AGENT, CandidateAgent, "proposed_agent", "foundry-candidate-agent-completeness"),
}


def _synthesize_one(
    pattern: EngineeringPattern,
    observations: list[EngineeringObservation],
    kind: str,
    client: ExtractionClient,
) -> CandidateSkill | CandidateTool | CandidateAgent:
    entity_type, candidate_cls, field_name, _suite_key = _KIND_CONFIG[kind]
    proposed_key = f"{kind}.{pattern.pattern_key}"
    prompt = build_candidate_prompt(pattern, observations, entity_type)
    raw = client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)
    payload = parse_candidate_content(
        raw, entity_type=entity_type, prompt=prompt, proposed_key=proposed_key
    )
    review = CandidateReview(
        proposed_key=proposed_key,
        derived_from_pattern_refs=[pattern.ref()],
        rationale=f"Synthesized from {pattern.frequency} recurring observations of "
        f"{pattern.common_activity} ({pattern.category}).",
    )
    return candidate_cls(
        name=f"candidate {kind}: {payload.name}",
        review=review,
        provenance=ProvenanceState.INFERRED,
        confidence=pattern.confidence,
        discovered_by=_SYNTHESIS_DISCOVERED_BY,
        **{field_name: payload},
    )


def run_foundry_cycle(
    service: ProjectGraphService,
    registry: MetamodelRegistry,
    metadata: MetadataRepository,
    graph: GraphRepository,
    project_ref: EntityRef,
    client: ExtractionClient,
    *,
    candidate_kinds: tuple[str, ...] = ("skill", "tool", "agent"),
    min_pattern_frequency: int = 2,
    on_error: Literal["fail_fast", "collect"] = "collect",
    now: datetime | None = None,
) -> FoundryCycleReport:
    """Mine ``project_ref``'s already-ingested graph, discover recurring
    patterns, synthesize a candidate per requested kind per pattern (the
    one LLM call), score each candidate's structural completeness, and
    advance its review status where a passing evaluation permits it.
    """
    timestamp = now or utc_now()
    failed: list[FoundryCycleFailure] = []

    facts = fetch_project_facts(project_ref, metadata, graph)
    observations = mine_observations(
        project_ref,
        pipelines=facts.pipelines,
        tests=facts.tests,
        delivery_tasks=facts.delivery_tasks,
        delivery_activities=facts.delivery_activities,
        discovered_by=_MINING_DISCOVERED_BY,
        now=timestamp,
    )
    for observation in observations:
        service.ingest_entity(observation)
        service.ingest_relationship(
            relationship(
                "OBSERVES", project_ref, observation.ref(), discovered_by=_MINING_DISCOVERED_BY
            ),
            registry,
        )

    patterns = discover_patterns(
        observations,
        project_ref=project_ref,
        min_frequency=min_pattern_frequency,
        discovered_by=_DISCOVERY_DISCOVERED_BY,
    )
    observations_by_ref = {str(observation.ref()): observation for observation in observations}
    for pattern in patterns:
        service.ingest_entity(pattern)
        for observation_ref in pattern.observation_refs:
            service.ingest_relationship(
                relationship(
                    "CONTRIBUTES_TO",
                    observation_ref,
                    pattern.ref(),
                    provenance=ProvenanceState.INFERRED,
                    confidence=pattern.confidence,
                    discovered_by=_DISCOVERY_DISCOVERED_BY,
                ),
                registry,
            )

    candidate_skills: list[CandidateSkill] = []
    candidate_tools: list[CandidateTool] = []
    candidate_agents: list[CandidateAgent] = []
    evaluations = []

    for pattern in patterns:
        pattern_observations = [
            observations_by_ref[str(ref)]
            for ref in pattern.observation_refs
            if str(ref) in observations_by_ref
        ]
        synthesized_any = False
        for kind in candidate_kinds:
            entity_type, _candidate_cls, _field_name, suite_key = _KIND_CONFIG[kind]
            try:
                candidate = _synthesize_one(pattern, pattern_observations, kind, client)
            except FoundryError as exc:
                failed.append(
                    FoundryCycleFailure(
                        kind="synthesis_failed",
                        detail=str(exc),
                        source=f"{kind}:{pattern.pattern_key}",
                    )
                )
                if on_error == "fail_fast":
                    raise
                continue

            service.ingest_entity(candidate)
            service.ingest_relationship(
                relationship(
                    "SYNTHESIZES",
                    pattern.ref(),
                    candidate.ref(),
                    provenance=ProvenanceState.INFERRED,
                    confidence=pattern.confidence,
                    discovered_by=_SYNTHESIS_DISCOVERED_BY,
                ),
                registry,
            )
            synthesized_any = True

            suite = registry.evaluation_suites.get(suite_key)
            if suite is None:
                failed.append(
                    FoundryCycleFailure(
                        kind="unknown_evaluation_suite",
                        detail=f"suite {suite_key!r} not found in registry",
                        source=f"{kind}:{pattern.pattern_key}",
                    )
                )
            else:
                observed_values = score_candidate_completeness(candidate, pattern)
                evaluation = run_suite(
                    suite,
                    registry.evaluation_metrics,
                    subject_ref=candidate.ref(),
                    observed_values=observed_values,
                    evaluated_at=timestamp,
                )
                service.ingest_entity(evaluation)
                evaluations.append(evaluation)
                try:
                    advance_candidate(
                        candidate, CandidateStatus.EVALUATED, evaluation=evaluation, now=timestamp
                    )
                except ValueError:
                    # Evaluation ran but did not pass the gate criteria --
                    # an expected outcome, not a Foundry failure. The
                    # candidate stays CANDIDATE.
                    pass
                else:
                    service.ingest_entity(candidate)

            if entity_type is EntityType.SKILL:
                candidate_skills.append(candidate)
            elif entity_type is EntityType.TOOL:
                candidate_tools.append(candidate)
            else:
                candidate_agents.append(candidate)

        if synthesized_any and not pattern.synthesized:
            pattern.synthesized = True
            service.ingest_entity(pattern)

    return FoundryCycleReport(
        project_ref=project_ref,
        observations=observations,
        patterns=patterns,
        candidate_skills=candidate_skills,
        candidate_tools=candidate_tools,
        candidate_agents=candidate_agents,
        evaluations=evaluations,
        failed=failed,
    )
